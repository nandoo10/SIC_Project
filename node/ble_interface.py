# node/ble_interface.py
import asyncio
from bleak import BleakClient, BleakScanner

CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
CHAT_MSG_UUID     = "12345678-1234-5678-1234-56789abcdef1"

class NodeClient:
    def __init__(self, adapter: str = "hci0"):
        self.adapter = adapter
        self.client = None
        self.chat_char = None

    async def scan_and_connect(self):
        print(f"[NODE] A procurar Sink com UUID {CHAT_SERVICE_UUID}...")
        
        # Procura dispositivos que anunciem o nosso serviço
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: CHAT_SERVICE_UUID.lower() in [u.lower() for u in ad.service_uuids],
            timeout=10.0,
            adapter=self.adapter
        )

        if not device:
            print("[NODE] Sink não encontrado. O Sink está a correr?")
            return False

        print(f"[NODE] Sink encontrado: {device.address}. A conectar...")
        self.client = BleakClient(device, adapter=self.adapter)

        try:
            await self.client.connect()
            print("[NODE] Conectado ao Sink!")
            
            # Encontrar a característica de escrita
            for service in self.client.services:
                for char in service.characteristics:
                    if char.uuid.lower() == CHAT_MSG_UUID.lower():
                        self.chat_char = char
                        break
            
            if self.chat_char:
                print("[NODE] Canal de comunicação pronto.")
                return True
            else:
                print("[NODE] Erro: Característica de chat não encontrada.")
                await self.client.disconnect()
                return False

        except Exception as e:
            print(f"[NODE] Erro na conexão: {e}")
            return False

    async def send_message(self, message):
        if self.client and self.client.is_connected and self.chat_char:
            await self.client.write_gatt_char(self.chat_char, message.encode("utf-8"))
            print(f"[NODE] Enviado: {message}")
        else:
            print("[NODE] Erro: Não está conectado.")

    async def run_loop(self):
        connected = await self.scan_and_connect()
        if not connected:
            return

        print("\n--- NODE PRONTO (Escreva mensagens para o Sink) ---")
        while True:
            msg = await asyncio.to_thread(input, "Mensagem > ")
            if msg.lower() == "sair":
                break
            await self.send_message(msg)
        
        await self.client.disconnect()
        print("[NODE] Desligado.")