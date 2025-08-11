"""
Función para obtener rutas escribibles
"""

import os
from pathlib import Path

def get_writable_config_path(filename):
    """Obtener ruta escribible para archivos de configuración"""
    
    # Intentar ubicaciones en orden de preferencia
    locations = [
        # Directorio actual
        Path('.') / filename,
        Path('config') / filename,
        
        # AppData del usuario
        Path(os.environ.get('APPDATA', '.')) / 'EtiquetadorZPL' / filename,
        
        # Temp como último recurso
        Path(os.environ.get('TEMP', '.')) / 'EtiquetadorZPL' / filename
    ]
    
    for path in locations:
        try:
            # Crear directorio padre si no existe
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Probar si se puede escribir
            test_file = path.parent / f'test_{os.getpid()}.tmp'
            test_file.write_text('test')
            test_file.unlink()
            
            return str(path)
            
        except (PermissionError, OSError):
            continue
    
    # Si nada funciona, usar directorio actual
    return filename

def get_readable_config_path(filename):
    """Obtener ruta legible para archivos de configuración"""
    
    locations = [
        Path('.') / filename,
        Path('config') / filename,
        Path(os.environ.get('APPDATA', '.')) / 'EtiquetadorZPL' / filename,
        Path(os.environ.get('TEMP', '.')) / 'EtiquetadorZPL' / filename
    ]
    
    for path in locations:
        if path.exists():
            return str(path)
    
    return None