# sink/sink.py
import sys
from ble_interface import start_server

# Se o seu PC usar o dongle é hci1, se usar o interno é hci0.
# Ajuste aqui conforme o seu 'hciconfig' no Ubuntu Host.
ADAPTER = "hci0" 

if __name__ == "__main__":
    # Inicia o servidor DBus
    start_server(ADAPTER)