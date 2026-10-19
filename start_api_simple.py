"""
Iniciar API simple
"""

import sys
from pathlib import Path

# Agregar paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))
sys.path.insert(0, str(project_root / "config"))

def ensure_console_title():
    """Playwright (Envios, Trabajos) lanza Node, que se cae con "Assertion failed:
    process_title" si la consola heredada no tiene titulo. Pasa al arrancar con
    `start "" ...` (restart_api_server.bat), asi que se le pone uno si falta."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        buffer = ctypes.create_unicode_buffer(256)
        if not kernel32.GetConsoleTitleW(buffer, len(buffer)):
            kernel32.SetConsoleTitleW("EtiquetadorZPL API")
    except Exception:
        pass


def start_api():
    """Iniciar API"""
    ensure_console_title()
    print("Iniciando API...")
    
    try:
        # Verificar dependencias
        import fastapi
        import uvicorn
        print(f"FastAPI: {fastapi.__version__}")
        print(f"Uvicorn: {uvicorn.__version__}")
    except ImportError as e:
        print(f"Error: Falta instalar dependencias: {e}")
        print("Ejecuta: pip install fastapi uvicorn")
        input("Presiona Enter...")
        return
    
    try:
        from fastapi_real import start_fastapi_server
        start_fastapi_server()
    except Exception as e:
        print(f"Error iniciando API: {e}")
        import traceback
        traceback.print_exc()
        input("Presiona Enter...")

if __name__ == "__main__":
    start_api()