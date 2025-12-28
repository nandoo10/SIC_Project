import sys
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import threading
import time

# UUIDs
CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
CHAT_MSG_UUID     = "12345678-1234-5678-1234-56789abcdef1"

# --- DBUS CONSTANTS ---
BLUEZ_SERVICE_NAME = 'org.bluez'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'
GATT_CHARACTERISTIC_IFACE = 'org.bluez.GattCharacteristic1'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'
class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'

# --- OBJETOS GATT ---
class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/org/bluez/example'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self): return dbus.ObjectPath(self.path)
    def add_service(self, service): self.services.append(service)

    @dbus.service.method('org.freedesktop.DBus.ObjectManager', out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.get_characteristics():
                response[chrc.get_path()] = chrc.get_properties()
        return response

class Service(dbus.service.Object):
    def __init__(self, bus, path, index, uuid, primary):
        self.path = path + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return { GATT_SERVICE_IFACE: { 'UUID': self.uuid, 'Primary': self.primary, 'Characteristics': dbus.Array(self.get_characteristic_paths(), signature='o') } }
    def get_path(self): return dbus.ObjectPath(self.path)
    def add_characteristic(self, characteristic): self.characteristics.append(characteristic)
    def get_characteristic_paths(self): return [c.get_path() for c in self.characteristics]
    def get_characteristics(self): return self.characteristics
    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface): return self.get_properties()[GATT_SERVICE_IFACE]

class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self): return { GATT_CHARACTERISTIC_IFACE: { 'Service': self.service.get_path(), 'UUID': self.uuid, 'Flags': self.flags } }
    def get_path(self): return dbus.ObjectPath(self.path)
    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface): return self.get_properties()[GATT_CHARACTERISTIC_IFACE]
    @dbus.service.method(GATT_CHARACTERISTIC_IFACE, in_signature='aya{sv}', out_signature='ay')
    def WriteValue(self, value, options): raise NotSupportedException()

class ChatChrc(Characteristic):
    def __init__(self, bus, index, service, callback):
        Characteristic.__init__(self, bus, index, CHAT_MSG_UUID, ['write', 'write-without-response', 'notify'], service)
        self.callback = callback 

    @dbus.service.method(GATT_CHARACTERISTIC_IFACE, in_signature='aya{sv}', out_signature='ay')
    def WriteValue(self, value, options):
        try:
            raw = bytes(value).decode("utf-8", errors="ignore")
            if self.callback:
                self.callback(raw)
        except Exception as e:
            print(f"[SERVER-ERR] {e}")
        return dbus.Array([], signature='y')

class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'
    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.local_name = "Init"
        self.service_uuids = [CHAT_SERVICE_UUID]
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        properties['LocalName'] = dbus.String(self.local_name)
        properties['ServiceUUIDs'] = dbus.Array(self.service_uuids, signature='s')
        properties['Includes'] = dbus.Array(["tx-power"], signature='s')
        return {LE_ADVERTISEMENT_IFACE: properties}

    def get_path(self): return dbus.ObjectPath(self.path)
    
    def update_local_name(self, new_name):
        self.local_name = new_name

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface): return self.get_properties()[LE_ADVERTISEMENT_IFACE]
    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature='', out_signature='')
    def Release(self): pass

# --- CLASSE GERAL DO SERVIDOR ---
class BLEServer:
    def __init__(self, adapter_interface, on_data_received, local_name):
        self.adapter_interface = adapter_interface
        self.on_data_received = on_data_received
        self.local_name = local_name
        self.mainloop = None
        self.bus = None
        self.thread = None
        
        self.ad_manager = None
        self.service_manager = None
        self.app = None
        self.adv = None
        self.retry_count = 0

    def _run(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()
        adapter_path = "/org/bluez/" + self.adapter_interface
        
        try:
            adapter = self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
            self.ad_manager = dbus.Interface(adapter, LE_ADVERTISING_MANAGER_IFACE)
            self.service_manager = dbus.Interface(adapter, GATT_MANAGER_IFACE)
        except Exception as e:
            print(f"[SERVER] Erro adaptador: {e}")
            return

        self.app = Application(self.bus)
        service = Service(self.bus, '/org/bluez/example/service', 0, CHAT_SERVICE_UUID, True)
        service.add_characteristic(ChatChrc(self.bus, 0, service, self.on_data_received))
        self.app.add_service(service)

        self.adv = Advertisement(self.bus, 0, 'peripheral')
        self.adv.update_local_name(self.local_name)

        def register_cb(): pass
        def register_error_cb(e): 
            if "AlreadyExists" not in str(e): print(f"[SERVER] Erro Registo: {e}")

        # Registo inicial
        self.service_manager.RegisterApplication(self.app.get_path(), {}, reply_handler=register_cb, error_handler=register_error_cb)
        self.ad_manager.RegisterAdvertisement(self.adv.get_path(), {}, reply_handler=register_cb, error_handler=register_error_cb)

        # --- CORREÇÃO DE VISIBILIDADE PERSISTENTE ---
        def device_connected_handler(interface, changed, invalidated, path):
            if interface == 'org.bluez.Device1' and 'Connected' in changed:
                connected = changed['Connected']
                if connected:
                    # Se alguém se conecta, tenta restaurar a visibilidade após 2s e 5s
                    # print(f"[SERVER] Conexão detetada. A restaurar visibilidade...")
                    GLib.timeout_add_seconds(2, self._force_restart_adv_internal)
                    GLib.timeout_add_seconds(5, self._force_restart_adv_internal)
                else:
                    # Se desconecta, restaura imediatamente
                    GLib.timeout_add_seconds(1, self._force_restart_adv_internal)

        self.bus.add_signal_receiver(device_connected_handler, dbus_interface="org.freedesktop.DBus.Properties", signal_name="PropertiesChanged", path_keyword="path")

        self.mainloop = GLib.MainLoop()
        try:
            self.mainloop.run()
        except:
            pass

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def update_advertisement(self, new_name):
        self.local_name = new_name
        if self.adv: self.adv.update_local_name(new_name)
        if self.mainloop: GLib.idle_add(self._force_restart_adv_internal)

    # --- TENTA FORÇAR O ANÚNCIO A FICAR ATIVO ---
    def _force_restart_adv_internal(self):
        # 1. Tenta Parar
        try: self.ad_manager.UnregisterAdvertisement(self.adv.get_path())
        except: pass
        
        # 2. Tenta Iniciar
        try: 
            self.ad_manager.RegisterAdvertisement(self.adv.get_path(), {}, reply_handler=lambda:None, error_handler=self._adv_error_handler)
            # print(f"[SERVER] Visibilidade restaurada: {self.local_name}")
            return False # Pára o timeout se tiver sucesso
        except:
            return True # Tenta de novo se falhar imediatamente

    def _adv_error_handler(self, error):
        # Se der erro (ex: AlreadyExists), agendamos nova tentativa
        # print(f"[SERVER] Aviso Adv: {error}. A tentar de novo...")
        GLib.timeout_add_seconds(2, self._force_restart_adv_internal)

    # --- RESTART TOTAL (RESET) ---
    def restart_server(self, new_name):
        self.local_name = new_name
        self.retry_count = 0
        if self.mainloop:
            GLib.idle_add(self._step1_shutdown)
    
    def _step1_shutdown(self):
        print(f"[SERVER] A desligar serviços (Kick)...")
        if self.ad_manager:
            try: self.ad_manager.UnregisterAdvertisement(self.adv.get_path())
            except: pass
        if self.service_manager:
            try: self.service_manager.UnregisterApplication(self.app.get_path())
            except: pass
        
        print(f"[SERVER] A aguardar 5s para garantir desconexão...")
        GLib.timeout_add_seconds(5, self._step2_start_services)
        return False

    def _step2_start_services(self):
        print(f"[SERVER] Tentativa {self.retry_count+1}: A iniciar como '{self.local_name}'")
        self.adv.update_local_name(self.local_name)
        
        try:
            self.service_manager.RegisterApplication(self.app.get_path(), {}, reply_handler=lambda:None, error_handler=self._on_register_error)
            self.ad_manager.RegisterAdvertisement(self.adv.get_path(), {}, reply_handler=lambda:None, error_handler=self._on_register_error)
        except Exception as e:
            self._on_register_error(e)
        return False

    def _on_register_error(self, error):
        err_str = str(error)
        if "AlreadyExists" in err_str or "NoReply" in err_str:
            try: self.ad_manager.UnregisterAdvertisement(self.adv.get_path())
            except: pass
            try: self.service_manager.UnregisterApplication(self.app.get_path())
            except: pass
            
            self.retry_count += 1
            if self.retry_count < 10: 
                GLib.timeout_add_seconds(2, self._step2_start_services)
            else:
                print("[SERVER] FALHA: Não foi possível reiniciar.")
        else:
            print(f"[SERVER] Erro: {err_str}")

    def stop(self):
        if self.mainloop:
            self.mainloop.quit()