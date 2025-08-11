import os
import sys
import configparser
import logging

# Hacer poppler opcional
try:
    from poppler_manager import get_poppler_path
except ImportError:
    def get_poppler_path():
        return None

def cargar_configuracion(archivo_ini="config.ini"):
    if not os.path.exists(archivo_ini):
        logging.warning("No se encontró config.ini. Generando uno de ejemplo.")
        # Obtener ruta automática de Poppler
        poppler_path = get_poppler_path() or "C:/Herramientas/poppler/Library/bin"
        
        # Crear directorios predeterminados
        entrada_path = "C:/EtiquetasFlex"
        salida_path = "C:/EtiquetasZPL"
        historial_path = "C:/EtiquetasHistorial"
        
        # Crear carpetas si no existen
        try:
            os.makedirs(entrada_path, exist_ok=True)
            os.makedirs(salida_path, exist_ok=True)
            os.makedirs(historial_path, exist_ok=True)
            logging.info(f"✅ Carpetas creadas: {entrada_path}, {salida_path}, {historial_path}")
        except Exception as e:
            logging.warning(f"⚠️ No se pudieron crear algunas carpetas: {e}")
        
        with open(archivo_ini, "w") as f:
            f.write(f"""[etiqueta]
ancho_mm = 100
alto_mm = 150

[impresora]
nombre = Godex GE300

[rutas]
entrada = {entrada_path}
salida = {salida_path}
historial = {historial_path}
poppler_path = {poppler_path}
""")
        logging.info("Editá el archivo generado y volvé a ejecutar.")
        return None

    try:
        config = configparser.ConfigParser()
        config.read(archivo_ini, encoding='utf-8')

        # Usar Poppler automático si no está configurado
        poppler_config = config["rutas"].get("poppler_path", "")
        try:
            if not poppler_config or not os.path.exists(poppler_config):
                poppler_config = get_poppler_path() or poppler_config
        except Exception:
            logging.warning("Poppler no disponible")
            
        # Obtener rutas de la configuración
        entrada_path = config["rutas"]["entrada"]
        salida_path = config["rutas"]["salida"]
        historial_path = config["rutas"]["historial"]
        
        # Crear carpetas si no existen
        try:
            os.makedirs(entrada_path, exist_ok=True)
            os.makedirs(salida_path, exist_ok=True)
            os.makedirs(historial_path, exist_ok=True)
            logging.info(f"✅ Carpetas verificadas/creadas")
        except Exception as e:
            logging.warning(f"⚠️ No se pudieron crear algunas carpetas: {e}")
        
        # Configuración de múltiples carpetas
        carpetas = []
        for i in range(1, 4):  # Hasta 3 carpetas
            seccion = f'carpeta{i}'
            if config.has_section(seccion):
                carpeta_config = {
                    'ruta': config.get(seccion, 'ruta', fallback=''),
                    'impresora': config.get(seccion, 'impresora', fallback=''),
                    'historial': config.get(seccion, 'historial', fallback=''),
                    'activa': config.getboolean(seccion, 'activa', fallback=True),
                    'recortar_pdf': config.getboolean(seccion, 'recortar_pdf', fallback=True),
                    'copias': config.getint(seccion, 'copias', fallback=1)
                }
                if carpeta_config['ruta']:  # Solo agregar si tiene ruta
                    carpetas.append(carpeta_config)
        
        # Si no hay carpetas configuradas, usar configuración antigua
        if not carpetas:
            carpetas.append({
                'ruta': entrada_path,
                'impresora': config["impresora"]["nombre"],
                'historial': historial_path,
                'activa': True,
                'recortar_pdf': True
            })
        
        return {
            "ancho_mm": int(config["etiqueta"]["ancho_mm"]),
            "alto_mm": int(config["etiqueta"]["alto_mm"]),
            "carpetas": carpetas,
            "poppler": poppler_config,
            # Mantener compatibilidad
            "impresora": config["impresora"]["nombre"],
            "entrada": entrada_path,
            "salida": salida_path,
            "historial": historial_path
        }
    except (configparser.Error, KeyError, ValueError) as e:
        logging.error(f"Error al leer configuración: {e}")
        return None
    except Exception as e:
        logging.exception(f"Error inesperado al cargar configuración: {e}")
        return None