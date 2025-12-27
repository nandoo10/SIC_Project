# node/node.py
import asyncio
from ble_interface import NodeClient

ADAPTER_VM = "hci0"

async def main_menu():
    node = NodeClient(adapter=ADAPTER_VM)
    
    while True:
        # Estado atual da conexão para mostrar no cabeçalho
        status = "DESCONECTADO"
        if node.client and node.client.is_connected:
            status = f"CONECTADO ({node.client.address})"

        print("\n" + "="*35)
        print(f"   IOT NODE | Status: {status}")
        print("="*35)
        print("1. Network Controls (Scan & List)")
        print("2. Conectar Automaticamente (Best Hop)")
        print("3. Conectar Manualmente (Escolher ID)")
        print("4. Desconectar Atual")     # <--- NOVA OPÇÃO
        print("5. Enviar Mensagem")       # <--- MOVEU-SE PARA BAIXO
        print("6. Sair")                  # <--- MOVEU-SE PARA BAIXO
        print("="*35)
        
        choice = await asyncio.to_thread(input, "Opção > ")

        if choice == "1":
            await node.scan_network_controls()
        
        elif choice == "2":
            await node.connect_best_candidate()

        elif choice == "3":
            if not node.candidates:
                print("\n[!] Lista vazia. Execute a opção 1 primeiro!")
                continue

            print("\n--- Candidatos Disponíveis ---")
            for i, c in enumerate(node.candidates):
                print(f"[{i}] {c['name']} (Hop {c['hop']}) | RSSI: {c['rssi']}")
            
            try:
                idx_str = await asyncio.to_thread(input, "Digite o ID para conectar: ")
                idx = int(idx_str)
                await node.connect_by_index(idx)
            except ValueError:
                print("[!] Por favor digite um número válido.")

        elif choice == "4":
            # Nova lógica de desconexão
            await node.disconnect()

        elif choice == "5":
            if node.client and node.client.is_connected:
                print("\n(Digite 'voltar' para sair do chat)")
                while True:
                    msg = await asyncio.to_thread(input, "Msg > ")
                    if msg.lower() == "voltar":
                        break
                    await node.send_message(msg)
            else:
                print("\n[!] Erro: Não está conectado (Use Opção 2 ou 3).")

        elif choice == "6":
            print("A encerrar...")
            await node.disconnect()
            break
        
        else:
            print("Opção inválida.")

if __name__ == "__main__":
    try:
        asyncio.run(main_menu())
    except KeyboardInterrupt:
        print("\nInterrompido.")