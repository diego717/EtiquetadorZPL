import os
import sys
import configparser
import logging
from src.config_manager import get_config_manager

# Hacer poppler opcional
try:
    from poppler_manager import get_poppler_path
except ImportError:
    def get_poppler_path():
        return None

def cargar_configuracion(archivo_ini="config.ini"):
    """Cargar configuración usando el gestor centralizado"""
    try:
        # Usar el gestor centralizado
        config_mgr = get_config_manager()
        config_data = config_mgr.load_config()
        
        if not config_data:
            logging.error("No se pudo cargar la configuración")
            return None
        
        # Obtener ruta de Poppler
        poppler_path = get_poppler_path() or "C:/Herramientas/poppler/Library/bin"
        
        # Convertir al formato esperado por la aplicación
        carpetas = config_data.get('carpetas', [])
        etiqueta = config_data.get('etiqueta', {})
        
        # Mantener compatibilidad con código existente
        if carpetas:
            primera_carpeta = carpetas[0]
            entrada_path = primera_carpeta.get('ruta', 'C:/EtiquetasFlex')
            impresora_nombre = primera_carpeta.get('impresora', 'Godex GE300')
            historial_path = primera_carpeta.get('historial', 'C:/EtiquetasFlex/Historial1')
        else:
            entrada_path = "C:/EtiquetasFlex"
            impresora_nombre = "Godex GE300"
            historial_path = "C:/EtiquetasFlex/Historial1"
        
        result = {
            "ancho_mm": etiqueta.get('ancho_mm', 100),
            "alto_mm": etiqueta.get('alto_mm', 150),
            "carpetas": carpetas,
            "poppler": poppler_path,
            # Mantener compatibilidad
            "impresora": impresora_nombre,
            "entrada": entrada_path,
            "salida": entrada_path,  # Usar misma carpeta
            "historial": historial_path
        }
        
        logging.info(f"Configuración cargada desde: {config_mgr.get_config_directory()}")
        return result
        
    except Exception as e:
        logging.error(f"Error en cargar_configuracion: {e}")
        return None

