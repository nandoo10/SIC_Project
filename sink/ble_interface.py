# sink/ble_interface.py
import asyncio
from bleak import BleakClient, BleakScanner

try:
    from common.messages import CHAT_SERVICE_UUID, CHAT_MSG_UUID
except ImportError:
    CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
    CHAT_MSG_UUID     = "12345678-1234-5678-1234-56789abcdef1"


class ConnectionManager:
    """
    Gere múltiplas ligações BLE em simultâneo.
    """
    def __init__(self, adapter: str = "hci0"):
        self.adapter = adapter
        # address -> { client, device, char_uuid }
        self.clients = {}

    @property
    def uplink_info(self):
        if not self.clients:
            return "Sem uplinks"
        return ", ".join(self.clients.keys())

    async def scan_devices(self, timeout: float = 5.0):
        print(f"\n[SCAN] A procurar dispositivos ({timeout}s)...")

        devices_dict = await BleakScanner.discover(
            adapter=self.adapter,
            timeout=timeout,
            return_adv=True
        )

        if not devices_dict:
            print("[SCAN] Nenhum dispositivo encontrado.")
            return []

        scanned_items = list(devices_dict.values())
        print(f"{'ID':<4} | {'Endereço MAC':<20} | {'Nome'}")
        print("-" * 60)
        for i, (device, adv) in enumerate(scanned_items):
            name = device.name or "Desconhecido"
            print(f"{i:<4} | {device.address:<20} | {name}")
        print("-" * 60)
        return scanned_items

    async def connect_to_device(self, device):
        addr = device.address

        if addr in self.clients:
            print(f"[CONNECT] Já ligado a {addr}")
            return True

        print(f"[CONNECT] A ligar a {addr} ({device.name})...")
        client = BleakClient(addr, adapter=self.adapter)

        try:
            await client.connect()
            if not client.is_connected:
                print("[CONNECT] Falha na ligação.")
                return False

            chat_char_uuid = None
            for service in client.services:
                if str(service.uuid).lower() == CHAT_SERVICE_UUID.lower():
                    for char in service.characteristics:
                        if str(char.uuid).lower() == CHAT_MSG_UUID.lower():
                            chat_char_uuid = char.uuid
                            break

            if not chat_char_uuid:
                print("[CONNECT] Serviço de chat não encontrado.")
                await client.disconnect()
                return False

            self.clients[addr] = {
                "client": client,
                "device": device,
                "char_uuid": chat_char_uuid
            }

            await self._start_notifications(addr)
            print(f"[CONNECT] Ligado com sucesso a {addr}")
            return True

        except Exception as e:
            print(f"[CONNECT] Erro: {e}")
            return False

    async def _start_notifications(self, addr):
        info = self.clients.get(addr)
        if not info:
            return

        def handler(sender, data):
            msg = data.decode("utf-8", errors="ignore")
            print(f"\n[{addr}] {msg}")

        await info["client"].start_notify(info["char_uuid"], handler)

    async def disconnect(self, addr=None):
        if addr:
            info = self.clients.pop(addr, None)
            if info:
                await info["client"].disconnect()
                print(f"[DISCONNECT] {addr} desligado.")
        else:
            for addr in list(self.clients.keys()):
                await self.disconnect(addr)

    async def send_message(self, addr, text: str):
        info = self.clients.get(addr)
        if not info:
            print("[CHAT] Nó não encontrado.")
            return
        try:
            await info["client"].write_gatt_char(
                info["char_uuid"],
                text.encode("utf-8")
            )
        except Exception as e:
            print(f"[CHAT] Erro: {e}")