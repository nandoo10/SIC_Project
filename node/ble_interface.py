# node/ble_interface.py
import asyncio
from bleak import BleakClient, BleakScanner

CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
CHAT_MSG_UUID     = "12345678-1234-5678-1234-56789abcdef1"
SINK_NAME_TARGET  = "Sink_Martim"

class NodeClient:
    def __init__(self, adapter: str = "hci0"):
        self.adapter = adapter
        self.client = None
        self.chat_char = None
        self.candidates = []

    async def scan_network_controls(self):
        """OPÇÃO 1: Network Controls - Faz scan e popula self.candidates"""
        print("\n--- [NETWORK CONTROL] A analisar topologia (5s)... ---")
        self.candidates = [] 
        
        try:
            scanned_devices = await BleakScanner.discover(
                timeout=5.0, 
                adapter=self.adapter,
                return_adv=True 
            )
        except Exception as e:
            print(f"[ERRO] Falha no scanner: {e}")
            return

        print(f"\nID | {'DEVICE NAME':<20} | {'MAC ADDRESS':<20} | {'RSSI':<5} | {'HOP'}")
        print("-" * 80)

        count = 0
        for device, adv_data in scanned_devices.values():
            name = device.name or adv_data.local_name or "Unknown"
            advertised_uuids = adv_data.service_uuids or []
            
            if CHAT_SERVICE_UUID.lower() in [u.lower() for u in advertised_uuids]:
                if SINK_NAME_TARGET in name:
                    hop_count = 0
                    hop_str = "0 (DIRECT)"
                else:
                    hop_count = 1 
                    hop_str = ">= 1 (RELAY)"

                self.candidates.append({
                    'device': device,
                    'hop': hop_count,
                    'name': name,
                    'rssi': adv_data.rssi
                })

                print(f"{count: <2} | {name:<20} | {device.address:<20} | {adv_data.rssi:<5} | {hop_str}")
                count += 1
            
        print("-" * 80)
        print(f"[RESULTADO] {len(self.candidates)} nós encontrados.")

    async def _connect_logic(self, device_obj):
        """Função auxiliar interna"""
        # Se já estiver conectado a outro, desliga primeiro
        if self.client and self.client.is_connected:
            print("[AVISO] A encerrar conexão anterior...")
            await self.disconnect()

        print(f"[NODE] A conectar a {device_obj.address}...")
        self.client = BleakClient(device_obj, adapter=self.adapter)
        try:
            await self.client.connect()
            print("[NODE] Conectado!")

            for service in self.client.services:
                for char in service.characteristics:
                    if char.uuid.lower() == CHAT_MSG_UUID.lower():
                        self.chat_char = char
                        break
            
            if self.chat_char:
                print("[NODE] Canal pronto. Pode enviar mensagens.")
                return True
            else:
                print("[ERRO] Serviço de Chat não encontrado.")
                await self.client.disconnect()
                return False
        except Exception as e:
            print(f"[ERRO] Falha ao conectar: {e}")
            self.client = None
            return False

    async def connect_best_candidate(self):
        """OPÇÃO 2"""
        if not self.candidates:
            print("[AVISO] Nenhum candidato. Execute 'Network Controls' primeiro.")
            return False

        self.candidates.sort(key=lambda x: x['rssi'], reverse=True)
        self.candidates.sort(key=lambda x: x['hop'])
        best = self.candidates[0]
        print(f"\n[AUTO] Escolhido: '{best['name']}' (Hop {best['hop']}).")
        return await self._connect_logic(best['device'])

    async def connect_by_index(self, index):
        """OPÇÃO 3"""
        if not self.candidates:
            print("[AVISO] Lista vazia. Faça Scan primeiro.")
            return False
        
        if 0 <= index < len(self.candidates):
            target = self.candidates[index]
            print(f"\n[MANUAL] A conectar a: '{target['name']}' (Hop {target['hop']})...")
            return await self._connect_logic(target['device'])
        else:
            print("[ERRO] ID inválido.")
            return False

    async def send_message(self, message):
        if self.client and self.client.is_connected and self.chat_char:
            try:
                await self.client.write_gatt_char(self.chat_char, message.encode("utf-8"))
                print(f"[TX] -> {message}")
            except Exception as e:
                print(f"[ERRO] Envio falhou: {e}")
        else:
            print("[ERRO] Não está conectado.")

    async def disconnect(self):
        """OPÇÃO 4: Desconectar"""
        if self.client and self.client.is_connected:
            print("[NODE] A desconectar...")
            try:
                await self.client.disconnect()
                print("[NODE] Desconectado com sucesso.")
            except Exception as e:
                print(f"[ERRO] Erro ao desconectar: {e}")
        else:
            print("[INFO] Sem conexão ativa.")
        
        # Limpar referências
        self.client = None
        self.chat_char = None