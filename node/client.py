import asyncio
from bleak import BleakClient, BleakScanner

# UUIDs do serviço e characteristic de chat
CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
CHAT_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"

# Endereço do dongle servidor (hci1)
SERVER_ADDRESS = 'E0:D3:62:D7:10:F8'

# Interface BLE do PC
CLIENT_INTERFACE = 'hci0'


async def main():
    print(f"📡 Usando o PC ({CLIENT_INTERFACE}) para procurar o Dongle ({SERVER_ADDRESS})...")

    device = await BleakScanner.find_device_by_address(
        SERVER_ADDRESS,
        adapter=CLIENT_INTERFACE,
        timeout=15.0
    )

    if not device:
        print(f"❌ Erro: O servidor {SERVER_ADDRESS} não foi encontrado.")
        return

    print(f"✅ Encontrado! Endereço: {device.address}")
    print("🔗 A conectar...")

    async with BleakClient(device, adapter=CLIENT_INTERFACE) as client:
        print("✅ Conectado com sucesso!")

        # Listagem
        print("\n📋 Lista de characteristics encontradas:")
        for service in client.services:
            print(f"\nServiço {service.uuid}:")
            for char in service.characteristics:
                print(f"  - UUID: {char.uuid} | Handle: {char.handle} | Properties: {char.properties}")
        print("\n-------------------------------------------------------\n")

        # Escolher characteristic automaticamente
        possible_chars = []

        for service in client.services:
            if service.uuid.lower() == CHAT_SERVICE_UUID.lower():
                for char in service.characteristics:
                    if char.uuid.lower() == CHAT_CHAR_UUID.lower():
                        possible_chars.append(char)

        if not possible_chars:
            print("❌ Nenhuma characteristic de chat encontrada!")
            return

        # Filtrar por notify + write
        possible_chars = [
            c for c in possible_chars
            if "notify" in c.properties and "write" in c.properties
        ]

        if not possible_chars:
            print("❌ Nenhuma characteristic com notify+write encontrada!")
            return

        # Escolher a de handle maior (normalmente a correta)
        chat_char = max(possible_chars, key=lambda c: c.handle)
        CHAT_HANDLE = chat_char.handle

        print(f"✅ Characteristic selecionada automaticamente! Handle = {CHAT_HANDLE}")

        # Handler receção
        def notification_handler(sender, data):
            print(f"\n📩 Recebido: {bytes(data).decode('utf-8')}\nVocê: ", end="", flush=True)

        await client.start_notify(CHAT_HANDLE, notification_handler)

        print("💬 Chat pronto! (Escreva 'sair' para terminar)")
        
        while True:
            msg = await asyncio.to_thread(input, "Você: ")

            if msg.strip().lower() == "sair":
                break

            if msg.strip():
                await client.write_gatt_char(CHAT_HANDLE, msg.encode("utf-8"))

        await client.stop_notify(CHAT_HANDLE)


if __name__ == "__main__":
    asyncio.run(main())
