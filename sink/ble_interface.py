# sink/ble_interface.py
import sys
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
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
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
# 1. CLASSE DE ADVERTISING (O CARTAZ)
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
        self.data = None
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
            
        # Intervalos para estabilidade (200ms)
        properties['MinInterval'] = dbus.UInt32(200)
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
        print(f'{self.path}: Released!')

# =========================================
# 2. CLASSES DE SERVIÇO GATT (A LOJA)
# =========================================
class Application(dbus.service.Object):
    def __init__(self, bus):
        # CORREÇÃO: Caminho específico para evitar erro "No object received"
        self.path = '/org/bluez/example' 
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        self.services.append(ChatService(bus, '/org/bluez/example/service', 0))

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
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
        # CORREÇÃO: O Serviço devolve UUID e Characteristics, NÃO Advertising
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

    # CORREÇÃO 1: Adicionar o decorator explicitamente com signatures de in/out
    @dbus.service.method(GATT_CHARACTERISTIC_IFACE, in_signature='aya{sv}', out_signature='ay')
    def WriteValue(self, value, options):
        # Converter os bytes recebidos para string
        try:
            raw = bytes(value).decode("utf-8", errors="ignore")
        except Exception:
            print("[ERRO] Falha ao decodificar bytes.")
            return dbus.Array([], signature='y')

        # CORREÇÃO 2: Parse seguro. Se falhar, retorna OK para não cair a conexão, mas avisa no log.
        try:
            nid, msg = raw.split("|", 1)
        except ValueError:
            print(f"[ERRO] Formato inválido recebido: {raw}")
            # Retornar array vazio diz ao BlueZ "Recebido, obrigado", mesmo que o formato esteja errado.
            return dbus.Array([], signature='y')

        # CORREÇÃO 3: Obter o endereço do remetente através do 'options' (Device Object Path)
        # O options['device'] vem como: "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
        device_path = str(options.get('device', ''))
        sender_address = "Desconhecido"
        
        if 'dev_' in device_path:
            # Extrai o MAC do final da string e substitui _ por :
            sender_address = device_path.split('dev_')[1].replace('_', ':')

        # 📒 Guardar forwarding (uplink) com o endereço real
        self.forwarding_table[nid] = sender_address

        print(f"[SINK RECEBEU] De: {sender_address} | NID: {nid} | Msg: {msg}")

        # Confirmação de sucesso para o cliente
        return dbus.Array([], signature='y')


class ChatService(Service):
    def __init__(self, bus, path, index):
        Service.__init__(self, bus, path, index, CHAT_SERVICE_UUID, True)
        self.add_characteristic(ChatQueue(bus, 0, self))

# =========================================
# 3. FUNÇÃO PRINCIPAL
# =========================================
def start_server(adapter_interface='hci1'):
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter_path = "/org/bluez/" + adapter_interface
    
    try:
        adapter_obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
        
        # Liga o adaptador se estiver desligado
        props_iface = dbus.Interface(adapter_obj, DBUS_PROP_IFACE)
        props_iface.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))
        
        service_manager = dbus.Interface(adapter_obj, GATT_MANAGER_IFACE)
        ad_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)
    except Exception as e:
        print(f"ERRO: Não encontrei o adaptador {adapter_interface}.")
        print(f"Verifique se o nome está correto (hci0 ou hci1) com 'hciconfig'.")
        print(f"Detalhe do erro: {e}")
        return

    app = Application(bus)
    adv = Advertisement(bus, 0, 'peripheral')

    mainloop = GLib.MainLoop()

    print(f"=== SINK (SERVER) A RODAR EM {adapter_interface} ===")
    
    def register_app_cb():
        print("1. Serviços GATT Registados OK.")
    
    def register_app_error_cb(error):
        print(f"ERRO GATT: {error}")
        mainloop.quit()

    def register_ad_cb():
        print(f"2. Advertising ATIVO! (Visível como '{LOCAL_NAME}')")
        print("--> A aguardar conexão do Node...")

    def register_ad_error_cb(error):
        print(f"ERRO ADVERTISING: {error}")
        mainloop.quit()

    # Registo da Aplicação
    service_manager.RegisterApplication(app.get_path(), dbus.Dictionary({}, signature='sv'),
                                        reply_handler=register_app_cb,
                                        error_handler=register_app_error_cb)

    # Registo do Anúncio
    ad_manager.RegisterAdvertisement(adv.get_path(), {},
                                     reply_handler=register_ad_cb,
                                     error_handler=register_ad_error_cb)

    try:
        mainloop.run()
    except KeyboardInterrupt:
        print("\nA encerrar...")
        ad_manager.UnregisterAdvertisement(adv.get_path())
        mainloop.quit()
