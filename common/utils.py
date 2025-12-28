# common/utils.py
import sys
import os

def select_adapter():
    """
    Permite escolher o adaptador via argumento de linha de comandos (ex: python sink.py hci1).
    Se não for passado nada, assume 'hci0'.
    """
    if len(sys.argv) > 1:
        adapter = sys.argv[1]
        print(f"[CONFIG] Adaptador selecionado manualmente: {adapter}")
        return adapter
    
    # Padrão
    print("[CONFIG] Nenhum adaptador especificado. A usar 'hci0' por defeito.")
    print("         (Para mudar, execute: python script.py hci1)")
    return "hci0"