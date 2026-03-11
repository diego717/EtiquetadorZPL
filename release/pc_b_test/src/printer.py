import os
import logging
from shutil import move, Error as ShutilError
from datetime import datetime
import win32print
from pathlib import Path

def send_raw_to_printer(data, impresora, job_name="Etiqueta"):
    """Envía datos raw a la impresora con manejo robusto de errores"""
    if not data:
        logging.error("No hay datos para imprimir")
        return False
        
    hPrinter = None
    try:
        hPrinter = win32print.OpenPrinter(impresora)
        hJob = win32print.StartDocPrinter(hPrinter, 1, (job_name, None, "RAW"))
        win32print.StartPagePrinter(hPrinter)
        win32print.WritePrinter(hPrinter, data)
        win32print.EndPagePrinter(hPrinter)
        win32print.EndDocPrinter(hPrinter)
        logging.info(f"🖨️ Trabajo '{job_name}' enviado a: {impresora}")
        return True
    except win32print.error as e:
        logging.error(f"Error de impresora al enviar '{job_name}': {e}")
        return False
    except Exception as e:
        logging.exception(f"Error inesperado al imprimir '{job_name}': {e}")
        return False
    finally:
        if hPrinter:
            try:
                win32print.ClosePrinter(hPrinter)
            except Exception as e:
                logging.warning(f"Error al cerrar impresora: {e}")

def imprimir_zpl_directo(contenido_zpl, impresora, copias=1):
    """Imprime contenido ZPL directamente con soporte para múltiples copias"""
    if not contenido_zpl or not contenido_zpl.strip():
        logging.error("Contenido ZPL vacío")
        return False
    
    # Sanitización final antes de imprimir
    from security import ZPLSanitizer
    contenido_sanitizado = ZPLSanitizer.sanitize_zpl_content(contenido_zpl)
    if not contenido_sanitizado:
        logging.error("ZPL no se pudo sanitizar para impresión")
        return False
    
    contenido_zpl = contenido_sanitizado
        
    try:
        data = contenido_zpl.encode("utf-8")
        
        # Imprimir las copias solicitadas
        success = True
        for i in range(copias):
            if not send_raw_to_printer(data, impresora, job_name=f"Etiqueta ZPL {i+1}/{copias}"):
                success = False
                break
            if copias > 1:
                logging.info(f"Copia {i+1} de {copias} enviada")
                
        return success
    except UnicodeEncodeError as e:
        logging.error(f"Error de codificación en ZPL: {e}")
        return False

def imprimir_zpl(zpl_path, impresora):
    """Imprime archivo ZPL con validaciones"""
    path = Path(zpl_path)
    
    if not path.exists():
        logging.error(f"El archivo ZPL no existe: {zpl_path}")
        return False
        
    if not path.is_file():
        logging.error(f"La ruta no es un archivo: {zpl_path}")
        return False
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            contenido = f.read()
            
        if not contenido.strip():
            logging.error(f"Archivo ZPL vacío: {zpl_path}")
            return False
            
        data = contenido.encode("utf-8")
        success = send_raw_to_printer(data, impresora, job_name="Etiqueta")
        
        if success:
            logging.info(f"🖨️ Archivo ZPL enviado a la impresora: {impresora}")
            
        return success
        
    except (OSError, IOError) as e:
        logging.error(f"Error al leer el archivo ZPL: {e}")
        return False
    except UnicodeDecodeError as e:
        logging.error(f"Error de codificación al leer ZPL: {e}")
        return False
    except Exception as e:
        logging.exception(f"Error inesperado al imprimir ZPL: {e}")
        return False

def mover_a_historial(pdf, zpl, imagen, recorte, carpeta):
    """Mueve archivos al historial con validaciones robustas"""
    if not carpeta:
        logging.error("Carpeta de historial no especificada")
        return False
        
    try:
        # Validar permisos antes de crear historial
        from permissions import permission_manager
        if not permission_manager.validate_directory_permissions(str(Path(carpeta).parent)):
            logging.error(f"Permisos insuficientes para crear historial en: {carpeta}")
            return False
        
        # Crear carpeta de historial de forma segura
        historial_path = Path(carpeta)
        historial_path.mkdir(parents=True, exist_ok=True)
        
        # Verificar permisos de escritura
        if not os.access(carpeta, os.W_OK):
            logging.error(f"Sin permisos de escritura en: {carpeta}")
            return False
            
        fecha = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        archivos_movidos = 0
        
        for archivo in [pdf, zpl, imagen, recorte]:
            if not archivo:
                continue
                
            archivo_path = Path(archivo)
            
            if not archivo_path.exists():
                logging.warning(f"⚠️ Archivo no encontrado para historial: {archivo}")
                continue
                
            if not archivo_path.is_file():
                logging.warning(f"⚠️ La ruta no es un archivo: {archivo}")
                continue
                
            try:
                # Generar nombre único para evitar conflictos
                nombre_base = f"{fecha}_{archivo_path.name}"
                destino = historial_path / nombre_base
                
                # Si el archivo ya existe, agregar sufijo
                contador = 1
                while destino.exists():
                    nombre_sin_ext = archivo_path.stem
                    extension = archivo_path.suffix
                    nombre_base = f"{fecha}_{nombre_sin_ext}_{contador}{extension}"
                    destino = historial_path / nombre_base
                    contador += 1
                    
                move(str(archivo_path), str(destino))
                logging.info(f"📁 Movido a historial: {archivo} → {destino}")
                archivos_movidos += 1
                
            except (ShutilError, OSError) as e:
                logging.error(f"❌ No se pudo mover {archivo} a historial: {e}")
            except Exception as e:
                logging.exception(f"Error inesperado al mover {archivo}: {e}")
                
        logging.info(f"📁 {archivos_movidos} archivos movidos al historial")
        return archivos_movidos > 0
        
    except Exception as e:
        logging.exception(f"Error crítico al mover archivos a historial: {e}")
        return False