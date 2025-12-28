import asyncio
import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.utils import select_adapter
from common.ble_server import BLEServer
from ble_interface import NodeClient

# --- VARIÁVEIS GLOBAIS ---
my_node_client = None
current_hop = -1
server = None
my_nid_short = "0000"
MAIN_LOOP = None
adapter_name = "hci0"

# --- FUNÇÃO NUCLEAR: RESET TOTAL ---
async def reset_network_state():
    global current_hop, server, my_nid_short
    
    # Se já estamos isolados, não faz nada
    if current_hop == -1 and server and "Hop:-1" in server.local_name:
        return

    print("\n[CASCADE] A resetar estado da rede...")
    current_hop = -1
    new_name = f"Node-{my_nid_short} [Hop:-1]"
    
    if server:
        # Chama o novo restart blindado
        print("[CASCADE] A reiniciar serviços (Expulsando Downlinks)...")
        server.restart_server(new_name)
    else:
        server = BLEServer(adapter_name, on_server_data_received, new_name)
        server.start()
    
    print("[RESET] Estado: Hop -1 (Isolado).")

def on_uplink_lost():
    global MAIN_LOOP
    if MAIN_LOOP and MAIN_LOOP.is_running():
        asyncio.run_coroutine_threadsafe(reset_network_state(), MAIN_LOOP)

# No node/node.py

def on_server_data_received(raw_data):
    global my_node_client, MAIN_LOOP
    
    # --- FILTRO DE PING ---
    # Se a mensagem for um PING de heartbeat, ignoramos silenciosamente
    if "PING" in raw_data:
        return
    # ----------------------

    if my_node_client and my_node_client.client and my_node_client.client.is_connected and MAIN_LOOP:
        print(f"\n[ROUTING] Recebido: {raw_data} -> A reencaminhar...")
        try:
            asyncio.run_coroutine_threadsafe(
                my_node_client.send_message(raw_data, is_forward=True), MAIN_LOOP
            )
        except: pass
    else:
        print(f"\n[DROP] Recebido: {raw_data} mas não tenho Uplink.")

async def main_menu():
    global my_node_client, server, current_hop, my_nid_short, MAIN_LOOP, adapter_name
    
    MAIN_LOOP = asyncio.get_running_loop()
    adapter_name = select_adapter()
    my_node_client = NodeClient(adapter=adapter_name)
    my_node_client.set_disconnect_handler(on_uplink_lost)
    
    my_nid_short = my_node_client.nid[-4:] if len(my_node_client.nid) >=4 else my_node_client.nid
    initial_name = f"Node-{my_nid_short} [Hop:-1]"
    
    print(f"[INIT] A iniciar servidor local como: {initial_name}")
    server = BLEServer(adapter_name, on_server_data_received, initial_name)
    server.start()

    while True:
        status = "DESCONECTADO (Uplink)"
        if my_node_client.client and my_node_client.client.is_connected:
            addr = my_node_client.client.address
            status = f"CONECTADO a {addr} (Meu Hop: {current_hop})"

        server_name = server.local_name if server else "Server OFF"

        print("\n" + "="*45)
        print(f"   NODE {my_nid_short} | {server_name}")
        print(f"   STATUS: {status}")
        print("="*45)
        print("1. Procurar (Scan)")
        print("2. Conectar Automático")
        print("3. Conectar Manualmente")
        print("4. Desconectar (Reset & Kick Downlinks)")
        print("5. Enviar Mensagem")
        print("6. Sair")
        print("="*45)
        
        try:
            choice = await asyncio.to_thread(input, "Opção > ")
        except EOFError: break

        if choice == "1":
            await my_node_client.scan_network_controls()
        
        elif choice == "2":
            print("[AUTO] A tentar conectar ao melhor candidato...")
            result_hop = await my_node_client.connect_best_candidate()
            
            if result_hop is not False:
                uplink_hop = result_hop
                current_hop = uplink_hop + 1
                new_name = f"Node-{my_nid_short} [Hop:{current_hop}]"
                if server: server.update_advertisement(new_name)
                print(f"[SUCESSO] Conectado a Hop {uplink_hop}. Sou agora Hop {current_hop}.")
            else:
                print("[FALHA] Não foi possível conectar.")

        elif choice == "3":
            if not my_node_client.candidates:
                print("\n[!] Lista vazia.")
                continue
            for i, c in enumerate(my_node_client.candidates):
                print(f"[{i}] {c['name']:<25} | Hop: {c['hop']} | RSSI: {c['rssi']}")
            try:
                idx = int(await asyncio.to_thread(input, "ID > "))
                if 0 <= idx < len(my_node_client.candidates):
                    target = my_node_client.candidates[idx]
                    if await my_node_client.connect_by_index(idx):
                        current_hop = target['hop'] + 1
                        new_name = f"Node-{my_nid_short} [Hop:{current_hop}]"
                        if server: server.update_advertisement(new_name)
                        print(f"[SUCESSO] Hop {current_hop}.")
            except ValueError: pass

        elif choice == "4":
            print("[MANUAL] A desligar Uplink...")
            
            # --- PROTEÇÃO CONTRA DUPLO RESET ---
            my_node_client.set_disconnect_handler(None) # Desativa callback temporariamente
            await my_node_client.disconnect()
            my_node_client.set_disconnect_handler(on_uplink_lost) # Restaura callback
            
            await reset_network_state()

        elif choice == "5":
            if my_node_client.client and my_node_client.client.is_connected:
                msg = await asyncio.to_thread(input, "Msg > ")
                await my_node_client.send_message(msg, is_forward=False)
            else: print("[!] Sem conexão.")

        elif choice == "6":
            await my_node_client.disconnect()
            if server: server.stop()
            break

if __name__ == "__main__":
    try: asyncio.run(main_menu())
    except KeyboardInterrupt: pass
