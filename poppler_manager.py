"""
Gestor de Poppler
"""

import os
from pathlib import Path

def get_poppler_path():
    """Obtener ruta de Poppler"""
    
    # 1. Verificar archivo de configuración local
    if Path('poppler_path.txt').exists():
        try:
            with open('poppler_path.txt', 'r') as f:
                path = f.read().strip()
            if Path(path).exists() and (Path(path) / 'pdftoppm.exe').exists():
                return path
        except:
            pass
    
    # 2. Verificar directorio local
    local_poppler = Path('poppler')
    if local_poppler.exists():
        for root, dirs, files in os.walk(local_poppler):
            if 'pdftoppm.exe' in files:
                path = str(Path(root))
                # Guardar ruta encontrada
                with open('poppler_path.txt', 'w') as f:
                    f.write(path)
                return path
    
    # 3. Verificar rutas comunes del sistema
    common_paths = [
        "C:/Program Files/poppler/bin",
        "C:/poppler/bin",
        "C:/tools/poppler/bin",
        "poppler/Library/bin",
        "poppler/poppler-23.08.0/Library/bin"  # Ruta específica existente
    ]
    
    for path in common_paths:
        if Path(path).exists() and (Path(path) / 'pdftoppm.exe').exists():
            return path
    
    # 4. Buscar en PATH del sistema
    try:
        import shutil
        pdftoppm_path = shutil.which('pdftoppm')
        if pdftoppm_path:
            return str(Path(pdftoppm_path).parent)
    except:
        pass
    
    return None

def install_poppler_if_needed():
    """Instalar Poppler si no está disponible"""
    if get_poppler_path():
        return True
    
    try:
        from install_poppler import install_poppler
        path = install_poppler()
        return path is not None
    except Exception as e:
        print(f"Error instalando Poppler: {e}")
        return False

if __name__ == "__main__":
    path = get_poppler_path()
    if path:
        print(f"Poppler encontrado: {path}")
    else:
        print("Poppler no encontrado. Ejecuta: python install_poppler.py")