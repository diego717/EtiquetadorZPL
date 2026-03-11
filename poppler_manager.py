"""
Gestor de Poppler
"""

import os
import sys
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
    
    # 2. Verificar directorio local (estructura del instalador)
    # Obtener directorio base de la aplicación
    if hasattr(os.sys, '_MEIPASS'):
        # Ejecutándose desde PyInstaller
        base_dir = Path(os.sys._MEIPASS)
    else:
        # Ejecutándose desde código fuente
        base_dir = Path(__file__).parent
    
    # Buscar poppler en la estructura del instalador
    poppler_paths = [
        base_dir / 'poppler' / 'poppler-23.08.0' / 'Library' / 'bin',
        base_dir / 'poppler' / 'Library' / 'bin',
        Path('poppler') / 'poppler-23.08.0' / 'Library' / 'bin',
        Path('poppler') / 'Library' / 'bin'
    ]
    
    for path in poppler_paths:
        if path.exists() and (path / 'pdftoppm.exe').exists():
            path_str = str(path)
            # Guardar ruta encontrada
            try:
                with open('poppler_path.txt', 'w') as f:
                    f.write(path_str)
            except:
                pass
            return path_str
    
    # 3. Verificar rutas comunes del sistema
    common_paths = [
        "C:/Program Files/poppler/bin",
        "C:/poppler/bin",
        "C:/tools/poppler/bin",
        "C:/Program Files/EtiquetadorZPL/poppler/poppler-23.08.0/Library/bin",
        "C:/Program Files (x86)/EtiquetadorZPL/poppler/poppler-23.08.0/Library/bin"
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