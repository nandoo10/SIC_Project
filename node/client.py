import asyncio
from bleak import BleakClient, BleakScanner

# UUIDs (Iguais ao servidor)
CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
CHAT_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"

# --- CONFIGURAÇÃO (Papéis Invertidos) ---
# SERVIDOR (Dongle/hci1)
SERVER_ADDRESS = 'E0:D3:62:D7:5E:98' 

# CLIENTE (PC/hci0)
CLIENT_INTERFACE = 'hci0'
# ------------------------------

async def main():
    print(f"📡 Usando o PC ({CLIENT_INTERFACE}) para procurar o Dongle ({SERVER_ADDRESS})...")
    
    # 1. SCAN
    device = await BleakScanner.find_device_by_address(
        SERVER_ADDRESS, 
        adapter=CLIENT_INTERFACE, 
        timeout=15.0
    )

    if not device:
        print(f"❌ Erro: O servidor {SERVER_ADDRESS} não foi encontrado.")
        print("   Verifique se o Terminal do Servidor está a fazer 'advertise on'!")
        return

    print(f"✅ Encontrado! Endereço: {device.address}")
    print("🔗 A conectar...")

    # 2. CONEXÃO
    async with BleakClient(device, adapter=CLIENT_INTERFACE) as client:
        print("✅ Conectado com sucesso!")

        # CORREÇÃO AQUI: Em versões novas do Bleak, não usamos get_services()
        # Usamos diretamente a propriedade client.services
        chat_char = None
        
        for service in client.services:
            if service.uuid.lower() == CHAT_SERVICE_UUID.lower():
                for char in service.characteristics:
                    if char.uuid.lower() == CHAT_CHAR_UUID.lower():
                        chat_char = char
                        break
            if chat_char: break

        if not chat_char:
            print("❌ Serviço de chat não encontrado.")
            print("   (Verifique se o gatt_server.py está a correr com os UUIDs certos)")
            # Listar o que foi encontrado para ajudar no debug
            print("   Serviços encontrados no servidor:")
            for s in client.services:
                print(f"   - {s.uuid}")
            return

        print("💬 Chat pronto! (Escreva 'sair' para terminar)")

        def notification_handler(sender, data):
            print(f"\n📩 Recebido: {bytes(data).decode('utf-8')}\nVocê: ", end="", flush=True)

        await client.start_notify(chat_char.uuid, notification_handler)

        while True:
            # Input não bloqueante
            msg = await asyncio.to_thread(input, "Você: ")
            
            if msg.strip().lower() == "sair": 
                break
            
            if msg.strip():
                # Enviar mensagem
                await client.write_gatt_char(chat_char.uuid, msg.encode("utf-8"))

        await client.stop_notify(chat_char.uuid)

if __name__ == "__main__":
    asyncio.run(main())