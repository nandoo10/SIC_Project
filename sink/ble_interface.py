import sys
import signal
import os
import dbus
import dbus.exceptions
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

# --- CONFIGURAÇÃO ---
CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
CHAT_MSG_UUID     = "12345678-1234-5678-1234-56789abcdef1"
LOCAL_NAME        = "Sink"

# --- INTERFACES BLUEZ ---
BLUEZ_SERVICE_NAME = 'org.bluez'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHARACTERISTIC_IFACE = 'org.bluez.GattCharacteristic1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'

class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'

# =========================================
# 1. CLASSE DE ADVERTISING
# =========================================
class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = [CHAT_SERVICE_UUID]
        self.local_name = LOCAL_NAME
        self.include_tx_power = True
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids, signature='s')
        if self.local_name:
            properties['LocalName'] = dbus.String(self.local_name)
        if self.include_tx_power:
            properties['Includes'] = dbus.Array(["tx-power"], signature='s')
        properties['MinInterval'] = dbus.UInt32(100)
        properties['MaxInterval'] = dbus.UInt32(200)
        return {LE_ADVERTISEMENT_IFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature='', out_signature='')
    def Release(self):
        pass

# =========================================
# 2. CLASSES DE SERVIÇO GATT
# =========================================
class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/org/bluez/example' 
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        self.services.append(ChatService(bus, '/org/bluez/example/service', 0))

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method('org.freedesktop.DBus.ObjectManager', out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
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
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(self.get_characteristic_paths(), signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristic_paths(self):
        return [c.get_path() for c in self.characteristics]

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]

class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHARACTERISTIC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHARACTERISTIC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHARACTERISTIC_IFACE]

    @dbus.service.method(GATT_CHARACTERISTIC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHARACTERISTIC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHARACTERISTIC_IFACE)
    def StartNotify(self):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHARACTERISTIC_IFACE)
    def StopNotify(self):
        raise NotSupportedException()

class ChatQueue(Characteristic):
    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index, CHAT_MSG_UUID, ['write', 'notify'], service
        )
        self.forwarding_table = {}

    @dbus.service.method(GATT_CHARACTERISTIC_IFACE, in_signature='aya{sv}', out_signature='ay')
    def WriteValue(self, value, options):
        # 1. Tentar descodificar
        try:
            raw = bytes(value).decode("utf-8", errors="ignore")
            print(f"[DEBUG] Recebido raw: {raw}") # Ver se chega aqui
        except Exception as e:
            print(f"[ERRO] Falha no decode: {e}")
            return dbus.Array([], signature='y')

        # 2. Tentar separar NID e Mensagem
        try:
            if "|" in raw:
                nid, msg = raw.split("|", 1)
            else:
                print(f"[ERRO] Mensagem sem '|': {raw}")
                # Retornamos sucesso na mesma para não crashar o Node
                return dbus.Array([], signature='y')
        except Exception as e:
            print(f"[ERRO] Falha no split: {e}")
            return dbus.Array([], signature='y')

        # 3. Tentar obter endereço do remetente
        try:
            device_path = str(options.get('device', ''))
            sender_address = "Desconhecido"
            if 'dev_' in device_path:
                sender_address = device_path.split('dev_')[1].replace('_', ':')
            
            self.forwarding_table[nid] = sender_address
            print(f"[SINK] De: {sender_address} | NID: {nid} | Msg: {msg}")
        except Exception as e:
            print(f"[ERRO] Falha ao processar remetente: {e}")

        # 4. RETORNO FINAL OBRIGATÓRIO
        return dbus.Array([], signature='y')


class ChatService(Service):
    def __init__(self, bus, path, index):
        Service.__init__(self, bus, path, index, CHAT_SERVICE_UUID, True)
        self.add_characteristic(ChatQueue(bus, 0, self))

# =========================================
# 3. FUNÇÃO PRINCIPAL (COM MENU DE SAÍDA '0')
# =========================================
def start_server(adapter_interface='hci0'):
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter_path = "/org/bluez/" + adapter_interface
    
    try:
        adapter_obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
        props_iface = dbus.Interface(adapter_obj, DBUS_PROP_IFACE)
        props_iface.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))
        service_manager = dbus.Interface(adapter_obj, GATT_MANAGER_IFACE)
        ad_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)
    except Exception as e:
        print(f"ERRO: Não encontrei o adaptador {adapter_interface}. {e}")
        return

    app = Application(bus)
    adv = Advertisement(bus, 0, 'peripheral')
    mainloop = GLib.MainLoop()

    print(f"=== SINK (SERVER) A RODAR EM {adapter_interface} ===")
    print("-----------------------------------------------------")
    print(" [NOTA] Para sair corretamente e não bloquear o BT:")
    print("        DIGITE '0' E DÊ ENTER.")
    print("-----------------------------------------------------")
    
    # --- CALLBACKS DO DBUS ---
    def register_app_cb(): print("1. Serviços GATT Registados OK.")
    def register_app_error_cb(error): 
        print(f"ERRO GATT: {error}")
        mainloop.quit()
    def register_ad_cb(): print(f"2. Advertising ATIVO! (Visível como '{LOCAL_NAME}') -> PRONTO.")
    def register_ad_error_cb(error):
        if "AlreadyExists" not in str(error): print(f"AVISO ADVERTISING: {error}")

    # --- FUNÇÃO DE LIMPEZA CENTRALIZADA ---
    def perform_cleanup():
        print("\n\n[!] A encerrar... A limpar Anúncios e a libertar o Bluetooth...")
        # 1. Tenta parar o Advertising para libertar o Hardware
        try:
            ad_manager.UnregisterAdvertisement(adv.get_path())
            print(" -> Anúncio removido com sucesso.")
        except Exception:
            pass 

        # 2. Sai do Loop principal
        try:
            mainloop.quit()
        except:
            pass

    # --- DETECTOR DE TECLA '0' ---
    def stdin_handler(source, condition):
        # Lê a linha digitada pelo utilizador
        try:
            line = sys.stdin.readline().strip()
            if line == '0':
                perform_cleanup()
                return False # Remove o watcher e sai
        except:
            pass
        return True # Continua a escutar

    # Adiciona o 'escuta' do teclado ao Loop do GLib
    GLib.io_add_watch(sys.stdin, GLib.IO_IN, stdin_handler)

    # --- GESTOR DE SINAIS (Caso feche o terminal no X) ---
    def signal_handler(sig, frame):
        print(f"\n[SISTEMA] Sinal de encerramento recebido ({sig}). A limpar...")
        perform_cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)

    # --- Lógica de Watchdog para manter visível ---
    def force_restart_advertising():
        try: ad_manager.UnregisterAdvertisement(adv.get_path())
        except: pass
        try:
            ad_manager.RegisterAdvertisement(adv.get_path(), {}, reply_handler=register_ad_cb, error_handler=register_ad_error_cb)
            return False
        except: return True

    def trigger_restart():
        force_restart_advertising()
        return False

    def device_connected_handler(interface, changed, invalidated, path):
        if interface == 'org.bluez.Device1':
            if 'Connected' in changed and changed['Connected']:
                print(f"\n[EVENTO] Novo Node conectado: {path}")
                GLib.timeout_add_seconds(5, trigger_restart)
            if 'Connected' in changed and not changed['Connected']:
                 print(f"\n[EVENTO] Node desconectado: {path}")
                 GLib.timeout_add_seconds(1, trigger_restart)

    bus.add_signal_receiver(device_connected_handler, dbus_interface="org.freedesktop.DBus.Properties", signal_name="PropertiesChanged", path_keyword="path")

    # Registar tudo
    service_manager.RegisterApplication(app.get_path(), dbus.Dictionary({}, signature='sv'), reply_handler=register_app_cb, error_handler=register_app_error_cb)
    ad_manager.RegisterAdvertisement(adv.get_path(), {}, reply_handler=register_ad_cb, error_handler=register_ad_error_cb)

    # Iniciar Loop
    try:
        mainloop.run()
    except KeyboardInterrupt:
        perform_cleanup()
