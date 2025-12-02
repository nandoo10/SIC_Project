#!/usr/bin/env python3
from pydbus import SystemBus
from gi.repository import GLib
import dbus
import dbus.service
import dbus.mainloop.glib
import sys

BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'

IOT_SERVICE_UUID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0000'
IOT_CHAR_UUID     = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0001'


# -------------------- Generic GATT Characteristic --------------------

class IotCharacteristic(dbus.service.Object):
    def __init__(self, bus, index, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.service = service
        self.uuid = IOT_CHAR_UUID
        self.flags = ['write', 'notify']
        self.value = []
        self.notifying = False

        super().__init__(bus, self.path)

    def get_properties(self):
        return {
            'org.bluez.GattCharacteristic1': {
                'UUID': self.uuid,
                'Service': self.service.get_path(),
                'Flags': self.flags,
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    # -------- Messages sent from remote clients --------
    @dbus.service.method('org.bluez.GattCharacteristic1',
                         in_signature='aya{sv}',
                         out_signature='ay')
    def WriteValue(self, value, options):
        msg = bytes(value).decode("utf-8")
        print(f"[SERVER] Received: {msg}")
        return []

    # --------- Notifications (server → clients) --------
    @dbus.service.method('org.bluez.GattCharacteristic1')
    def StartNotify(self):
        print("[SERVER] Client subscribed for notifications")
        self.notifying = True

    @dbus.service.method('org.bluez.GattCharacteristic1')
    def StopNotify(self):
        print("[SERVER] Client unsubscribed")
        self.notifying = False

    @dbus.service.signal(DBUS_PROP_IFACE, signature='sa{sv}as')
    def PropertiesChanged(self, iface, changed, invalidated):
        pass

    # Send a message to all connected clients
    def send_notification(self, text):
        if not self.notifying:
            return
        payload = [dbus.Byte(c) for c in text.encode("utf-8")]
        self.PropertiesChanged(
            'org.bluez.GattCharacteristic1',
            {'Value': payload},
            []
        )
        print(f"[SERVER] Sent notification: {text}")


# -------------------- GATT Service --------------------

class IotService(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = f"/org/bluez/iot/service{index}"
        self.bus = bus
        self.uuid = IOT_SERVICE_UUID
        self.primary = True
        super().__init__(bus, self.path)

        self.char = IotCharacteristic(bus, 0, self)

    def get_properties(self):
        return {
            'org.bluez.GattService1': {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': [self.char.get_path()],
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)


# -------------------- Application --------------------

class IotApplication(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, "/")
        self.service = IotService(bus, 0)

    @dbus.service.method('org.freedesktop.DBus.ObjectManager',
                         out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {
            self.service.get_path(): self.service.get_properties(),
            self.service.char.get_path(): self.service.char.get_properties(),
        }
        return response


# -------------------- MAIN --------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: sudo python3 iot_ble_server.py hci0")
        return

    hci = sys.argv[1]

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter_path = f"/org/bluez/{hci}"
    adapter = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
    gatt_manager = dbus.Interface(adapter, GATT_MANAGER_IFACE)

    app = IotApplication(bus)

    print("[SERVER] Registering IOT GATT application...")
    gatt_manager.RegisterApplication(app.get_path(), {})

    print("[SERVER] Ready. Waiting for BLE clients…")
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
