# node/node.py
import asyncio
from ble_interface import NodeClient

# Na VM, o dongle geralmente é hci0 (porque é o único lá dentro)
ADAPTER_VM = "hci0"

if __name__ == "__main__":
    node = NodeClient(adapter=ADAPTER_VM)
    try:
        asyncio.run(node.run_loop())
    except KeyboardInterrupt:
        pass