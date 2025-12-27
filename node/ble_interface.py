# node/ble_interface.py
import asyncio
import uuid
from bleak import BleakClient, BleakScanner

CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
CHAT_MSG_UUID     = "12345678-1234-5678-1234-56789abcdef1"
SINK_NAME_TARGET  = "Sink"


class NodeClient:
    def __init__(self, adapter: str = "hci0"):
        self.adapter = adapter
        self.client = None
        self.chat_char = None
        self.candidates = []

        # 🔑 NID único do Node (128-bit)
        self.nid = uuid.uuid4().hex
        print(f"[NODE] NID atribuído: {self.nid}")

    async def scan_network_controls(self):
        print("\n--- [NETWORK CONTROL] A analisar topologia (5s)... ---")
        self.candidates = [] 
        
        scanned_devices = await BleakScanner.discover(
            timeout=5.0, 
            adapter=self.adapter,
            return_adv=True 
        )

        print(f"\nID | {'DEVICE NAME':<20} | {'MAC ADDRESS':<20} | {'RSSI':<5} | {'HOP'}")
        print("-" * 80)

        count = 0
        for device, adv_data in scanned_devices.values():
            name = device.name or adv_data.local_name or "Unknown"
            advertised_uuids = adv_data.service_uuids or []

            if CHAT_SERVICE_UUID.lower() in [u.lower() for u in advertised_uuids]:
                hop = 0 if SINK_NAME_TARGET in name else 1

                self.candidates.append({
                    'device': device,
                    'hop': hop,
                    'name': name,
                    'rssi': adv_data.rssi
                })

                print(f"{count:<2} | {name:<20} | {device.address:<20} | {adv_data.rssi:<5} | {hop}")
                count += 1

        print("-" * 80)
        print(f"[RESULTADO] {len(self.candidates)} nós encontrados.")

    async def _connect_logic(self, device_obj):
        if self.client and self.client.is_connected:
            await self.disconnect()

        self.client = BleakClient(device_obj, adapter=self.adapter)
        await self.client.connect()

        for service in self.client.services:
            for char in service.characteristics:
                if char.uuid.lower() == CHAT_MSG_UUID.lower():
                    self.chat_char = char
                    return True

        await self.client.disconnect()
        return False

    async def connect_best_candidate(self):
        self.candidates.sort(key=lambda x: (x['hop'], -x['rssi']))
        return await self._connect_logic(self.candidates[0]['device'])

    async def connect_by_index(self, index):
        return await self._connect_logic(self.candidates[index]['device'])

    async def send_message(self, message):
        if not self.client or not self.chat_char:
            return

        # 📦 FORMATO: NID|MENSAGEM
        payload = f"{self.nid}|{message}"
        await self.client.write_gatt_char(
            self.chat_char,
            payload.encode("utf-8")
        )
        print(f"[TX] -> {message}")

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
        self.client = None
        self.chat_char = None
