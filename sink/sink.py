import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from common.utils import select_adapter
    from common.ble_server import BLEServer
except ImportError as e:
    print(f"Erro import: {e}")
    sys.exit(1)

def on_msg_received(raw_data):
    # LÃ³gica do Sink: Apenas mostra a mensagem
    if "|" in raw_data:
        nid, msg = raw_data.split("|", 1)
        print(f"[SINK RECV] De: {nid} | Msg: {msg}")
    else:
        print(f"[SINK RECV] {raw_data}")

if __name__ == "__main__":
    adapter = select_adapter()
    
    # Sink tem Hop 0 fixo
    server = BLEServer(adapter, on_msg_received, "Sink [Hop:0]")
    
    print(f"=== SINK INICIADO ({adapter}) ===")
    server.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nA sair...")
        server.stop()
