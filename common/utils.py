# common/utils.py
import os

def get_hci_by_mac(target_mac):
    """
    Procura qual interface (hci0, hci1, etc.) corresponde ao MAC desejado.
    Lê diretamente de /sys/class/bluetooth para ser rápido e fiável.
    """
    target = target_mac.strip().upper()
    base_dir = '/sys/class/bluetooth'
    
    if not os.path.exists(base_dir):
        print("ERRO: Sistema Bluetooth não detetado (Linux apenas).")
        return "hci0" # Fallback

    # Lista todas as pastas (hci0, hci1...)
    for device_name in os.listdir(base_dir):
        if device_name.startswith('hci'):
            try:
                # Lê o endereço MAC real do dispositivo
                with open(f'{base_dir}/{device_name}/address', 'r') as f:
                    address = f.read().strip().upper()
                    
                if address == target:
                    print(f"--> Hardware '{target}' detetado em: {device_name}")
                    return device_name
            except Exception:
                continue
                
    print(f"AVISO: Dispositivo {target_mac} não encontrado! A usar 'hci0' por defeito.")
    return "hci0"