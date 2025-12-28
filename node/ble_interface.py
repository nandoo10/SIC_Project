import asyncio
import os  # alterado para usar os.urandom
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
        self._watchdog_task = None 

        # NID único de 128 bits (16 bytes)
        self.nid = os.urandom(16).hex()  # hex string de 32 caracteres
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
                    self.candidates.append({'device': d, 'hop': hop_count, 'name': local_name, 'rssi': adv.rssi})
                    print(f"{count:<3} | {local_name:<25} | {hop_count:<5} | {adv.rssi}")
                    count += 1
        except Exception as e:
            print(f"[ERRO SCAN] {e}")

    async def _connect_logic(self, device_obj):
        if self.client and self.client.is_connected:
            await self.disconnect()

        print(f"[CONNECT] A conectar a {device_obj.address}...")
        try:
            self.client = BleakClient(
                device_obj, 
                adapter=self.adapter, 
                disconnected_callback=self._internal_on_disconnect,
                timeout=10.0
            )
            await self.client.connect()
            
            for service in self.client.services:
                for char in service.characteristics:
                    if char.uuid.lower() == CHAT_MSG_UUID.lower():
                        self.chat_char = char
                        print(f"[CONNECT] Serviço de Chat encontrado!")
                        self._start_watchdog()
                        return True
            
            print("[ERRO] Serviço não encontrado.")
            await self.client.disconnect()
            return False
            
        except Exception as e:
            print(f"[ERRO CONEXÃO] {e}")
            self.client = None
            return False

    def _internal_on_disconnect(self, client):
        if self.client is None: return
        print("\n[ALERTA] Ligação Perdida (Detetado pelo Cliente)!")
        self._stop_watchdog()
        self.client = None 
        if self.on_disconnect_callback:
            self.on_disconnect_callback()

    # --- WATCHDOG ATIVO (PING) ---
    def _start_watchdog(self):
        if self._watchdog_task: return
        self._watchdog_task = asyncio.create_task(self._active_ping_loop())

    def _stop_watchdog(self):
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None

    async def _active_ping_loop(self):
        """ Envia um pacote PING a cada 2s com TIMEOUT RÍGIDO. """
        while True:
            await asyncio.sleep(2.0)
            if self.client and self.client.is_connected and self.chat_char:
                try:
                    payload = f"{self.nid}|PING".encode("utf-8")
                    await asyncio.wait_for(
                        self.client.write_gatt_char(self.chat_char, payload, response=True),
                        timeout=1.0
                    )
                except Exception as e:
                    print(f"\n[WATCHDOG] Ping falhou/timeout ({type(e).__name__}). A cortar ligação...")
                    self._internal_on_disconnect(self.client)
                    break
            else:
                break
    # -----------------------------

    async def connect_best_candidate(self):
        if not self.candidates:
            print("[AVISO] Lista vazia.")
            return False
        valid = [c for c in self.candidates if c['hop'] >= 0]
        if not valid:
            print("[BLOQUEIO] Sem dispositivos válidos.")
            return False
        valid.sort(key=lambda x: (x['hop'], -x['rssi']))
        best = valid[0]
        print(f"[AUTO] A conectar a: {best['name']}")
        res = await self._connect_logic(best['device'])
        return best['hop'] if res else False

    async def connect_by_index(self, index):
        if not self.candidates or index >= len(self.candidates): return False
        t = self.candidates[index]
        if t['hop'] < 0:
            print("[BLOQUEIO] Hop -1.")
            return False
        return await self._connect_logic(t['device'])

    async def send_message(self, message, is_forward=False):
        if not self.client or not self.chat_char:
            print("[ERRO] Não conectado.")
            return
        try:
            payload = message if is_forward else f"{self.nid}|{message}"
            await self.client.write_gatt_char(self.chat_char, payload.encode("utf-8"), response=True)
            if not is_forward: print(f"[TX] -> {message}")
        except Exception:
            self._internal_on_disconnect(self.client)

    async def disconnect(self):
        self._stop_watchdog()
        if self.client:
            try: await self.client.disconnect()
            except: pass
        self.client = None