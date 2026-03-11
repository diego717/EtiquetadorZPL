import sys
import os
from pathlib import Path

# Agregar paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))

# Cambiar directorio de trabajo
os.chdir(str(project_root))

# Importar y ejecutar la API
from api.fastapi_real import start_fastapi_server

if __name__ == "__main__":
    start_fastapi_server()