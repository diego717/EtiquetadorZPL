"""
Configuración de logging para EtiquetadorZPL
Ahora usa el gestor centralizado de configuración
"""

import logging
from src.config_manager import get_config_manager

def setup_logging():
    """Configurar logging usando el gestor centralizado"""
    try:
        config_mgr = get_config_manager()
        # El logging ya está configurado en el constructor del ConfigManager
        logging.info("Sistema de logging inicializado")
        return config_mgr.get_log_directory()
    except Exception as e:
        print(f"Error configurando logging: {e}")
        return None

def get_log_directory():
    """Obtener directorio de logs"""
    try:
        config_mgr = get_config_manager()
        return config_mgr.get_log_directory()
    except Exception as e:
        print(f"Error obteniendo directorio de logs: {e}")
        return None