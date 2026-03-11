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

def start_api():
    """Iniciar API"""
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