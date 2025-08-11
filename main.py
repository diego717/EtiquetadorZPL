"""
EtiquetadorZPL - Launcher Principal
"""

import sys
from pathlib import Path

# Agregar carpetas al path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))
sys.path.insert(0, str(project_root / "gui"))

def main():
    """Menu principal"""
    print("=== EtiquetadorZPL ===")
    print("1. Iniciar GUI")
    print("2. Iniciar Servicio")
    print("3. Iniciar API solamente")
    print("4. Tests del sistema")
    print("5. Salir")
    
    choice = input("Selecciona opcion (1-5): ")
    
    if choice == "1":
        from gui.launcher import main as gui_main
        gui_main()
    elif choice == "2":
        from api.simple_service import main as service_main
        service_main()
    elif choice == "3":
        from api.fast_api import start_fast_api
        start_fast_api()
    elif choice == "4":
        from tests.test_system import main as test_main
        test_main()
    elif choice == "5":
        return
    else:
        print("Opcion invalida")
        main()

if __name__ == "__main__":
    main()
