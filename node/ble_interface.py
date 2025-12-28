import asyncio
import uuid
from bleak import BleakClient, BleakScanner

# UUIDs do Projeto
CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
CHAT_MSG_UUID     = "12345678-1234-5678-1234-56789abcdef1"

class NodeClient:
    def __init__(self, adapter: str = "hci0"):
        self.adapter = adapter
        self.client = None
        self.chat_char = None
        self.candidates = []
        self.on_disconnect_callback = None

        # NID único (8 chars)
        self.nid = uuid.uuid4().hex[:8]
        print(f"[NODE] NID atribuído: {self.nid}")

    def set_disconnect_handler(self, callback):
        self.on_disconnect_callback = callback

    async def scan_network_controls(self):
        print("\n--- [SCAN] A procurar Uplinks... ---")
        self.candidates = [] 
        
        try:
            devices_dict = await BleakScanner.discover(
                timeout=3.0, adapter=self.adapter, return_adv=True 
            )

            print(f"\n{'ID':<3} | {'DEVICE NAME':<25} | {'HOP':<5} | {'RSSI'}")
            print("-" * 60)

            count = 0
            for d, adv in devices_dict.values():
                uuids = adv.service_uuids or []
                if CHAT_SERVICE_UUID.lower() in [u.lower() for u in uuids]:
                    local_name = d.name or adv.local_name or "Unknown"
                    
                    hop_count = 0 if "Sink" in local_name else 99
                    try:
                        if "[Hop:" in local_name:
                            part = local_name.split("[Hop:")[1]
                            hop_count = int(part.split("]")[0])
                    except: pass
                    
                    self.candidates.append({
                        'device': d, 'hop': hop_count, 'name': local_name, 'rssi': adv.rssi
                    })
                    print(f"{count:<3} | {local_name:<25} | {hop_count:<5} | {adv.rssi}")
                    count += 1
            
        except Exception as e:
            print(f"[ERRO SCAN] {e}")

    async def _connect_logic(self, device_obj):
        if self.client and self.client.is_connected:
            await self.disconnect()

        print(f"[CONNECT] A conectar a {device_obj.address}...")
        try:
            self.client = BleakClient(device_obj, adapter=self.adapter, disconnected_callback=self._internal_on_disconnect)
            await self.client.connect()
            
            for service in self.client.services:
                for char in service.characteristics:
                    if char.uuid.lower() == CHAT_MSG_UUID.lower():
                        self.chat_char = char
                        print(f"[CONNECT] Serviço de Chat encontrado!")
                        return True
            
            print("[ERRO] Serviço de Chat não encontrado no alvo.")
            await self.client.disconnect()
            return False
            
        except Exception as e:
            print(f"[ERRO CONEXÃO] {e}")
            self.client = None
            return False

    def _internal_on_disconnect(self, client):
        print("\n[ALERTA] O Uplink desconectou-se!")
        if self.on_disconnect_callback:
            self.on_disconnect_callback()

    async def connect_best_candidate(self):
        """
        Retorna:
          - Inteiro (Hop Count do pai) se sucesso.
          - False se falha.
        """
        if not self.candidates:
            print("[AVISO] Lista vazia. Faça scan primeiro.")
            return False
        
        # Filtra Hop >= 0 e ordena
        valid_candidates = [c for c in self.candidates if c['hop'] >= 0]
        if not valid_candidates:
            print("[BLOQUEIO] Não há dispositivos válidos (Hop >= 0).")
            return False

        valid_candidates.sort(key=lambda x: (x['hop'], -x['rssi']))
        best = valid_candidates[0]
        
        print(f"[AUTO] Escolhido pelo Sistema: {best['name']} (Hop {best['hop']})")
        
        success = await self._connect_logic(best['device'])
        if success:
            return best['hop'] # <--- RETORNA O HOP REAL AQUI
        return False

    async def connect_by_index(self, index):
        if not self.candidates or index >= len(self.candidates): return False
        target = self.candidates[index]
        if target['hop'] < 0:
            print(f"\n[BLOQUEIO] '{target['name']}' tem Hop -1. Não pode ser Uplink.")
            return False
        return await self._connect_logic(target['device'])

    async def send_message(self, message, is_forward=False):
        if not self.client or not self.chat_char:
            print("[ERRO] Não conectado.")
            return
        try:
            payload = message if is_forward else f"{self.nid}|{message}"
            await self.client.write_gatt_char(self.chat_char, payload.encode("utf-8"), response=True)
            if not is_forward: print(f"[TX] -> {message}")
        except Exception as e:
            print(f"[ERRO TX] {e}")

    async def disconnect(self):
        if self.client:
            try: await self.client.disconnect()
            except: pass
        self.client = None
        self.chat_char = None
