import os
import logging
import requests
import io
import subprocess
import socket
from shutil import unpack_archive, ReadError
from watchdog.events import FileSystemEventHandler
from PIL import Image

from queue import Queue
from threading import Event, Thread
from pathlib import Path
from validacion import validar_archivo_zpl, validar_directorio
from security import SecurityValidator, resource_monitor, ZPLSanitizer
from security_logger import security_logger
from permissions import permission_manager

# from gui import mostrar_vista_previa  # Eliminado - solo interfaz grÃ¡fica
from printer import imprimir_zpl_directo, mover_a_historial
from pdf_printer import imprimir_png

# Constantes
MAX_ZIP_SIZE_MB = 100
MAX_TXT_SIZE_KB = 500
ENCODINGS = ['utf-8', 'latin-1', 'cp1252']
LABELARY_URL = "https://api.labelary.com/v1/printers/8dpmm/labels/4x6/0/"
LABELARY_HEADERS = {
    'Accept': 'image/png', # Especificar que quieres una imagen
    'Content-Type': 'application/x-www-form-urlencoded'
}
class PDFHandler(FileSystemEventHandler):
    def __init__(self, config, observer=None, root=None):
        self.config = config
        self.observer = observer
        self.root = root  # Referencia a la ventana principal
        
        # Configurar logging si no estÃ¡ configurado
        try:
            from log_config import setup_logging
            setup_logging()
        except Exception as e:
            print(f"Error configurando logs: {e}")
        
        # InformaciÃ³n del sistema para logs
        self.system_info = self._get_system_info()
        
        # Debug: verificar si root estÃ¡ disponible
        if self.root:
            logging.info(f"Handler inicializado CON GUI para carpeta: {config.get('entrada', 'N/A')}")
        else:
            logging.warning(f"Handler inicializado SIN GUI para carpeta: {config.get('entrada', 'N/A')}")
        
        # Log de informaciÃ³n del sistema
        logging.info(f"SISTEMA: {self.system_info['computer']} | USUARIO: {self.system_info['user']} | IP: {self.system_info['ip']}")
        self.process_queue = Queue(maxsize=100)
        self.stop_event = Event()
        self.processing_thread = None
        self.archivos_procesando = set()
        self.archivos_extraidos = set()  # Archivos reciÃ©n extraÃ­dos de ZIP
        self.ignorar_archivos = set()  # Archivos a ignorar permanentemente
        self.carpeta_numero = getattr(self, 'carpeta_numero', 1)  # NÃºmero de carpeta para logs
        
        if not self.config:
            raise ValueError("ConfiguraciÃ³n no vÃ¡lida")
        
        # Log de debug para verificar configuraciÃ³n
        carpeta_entrada = self.config.get('entrada', 'N/A')
        logging.info(f"Handler inicializado - Carpeta: {carpeta_entrada}")
        logging.info(f"Carpeta existe: {Path(carpeta_entrada).exists() if carpeta_entrada != 'N/A' else False}")
        
        # Validar permisos de carpeta
        if carpeta_entrada != 'N/A':
            if not permission_manager.validate_directory_permissions(carpeta_entrada):
                logging.error(f"Permisos insuficientes en carpeta: {carpeta_entrada}")
        
        # Validar acceso a impresora
        impresora = self.config.get('impresora')
        if impresora:
            permission_manager.validate_printer_access(impresora)
            
        self.start_processing_thread()
    
    def _get_system_info(self):
        """Obtener informaciÃ³n del sistema para identificaciÃ³n"""
        try:
            computer_name = os.environ.get('COMPUTERNAME', 'UNKNOWN')
            username = os.environ.get('USERNAME', 'UNKNOWN')
            
            # Obtener IP local
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except:
                local_ip = "UNKNOWN"
            
            return {
                'computer': computer_name,
                'user': username,
                'ip': local_ip
            }
        except Exception as e:
            logging.error(f"Error obteniendo informaciÃ³n del sistema: {e}")
            return {
                'computer': 'UNKNOWN',
                'user': 'UNKNOWN', 
                'ip': 'UNKNOWN'
            }
        
    def _log_to_gui(self, mensaje):
        """EnvÃ­a mensaje directamente al log de la GUI"""
        if hasattr(self, 'gui_instance') and self.gui_instance:
            self.gui_instance.log_message(mensaje)
        else:
            print(f"GUI LOG: {mensaje}")
        
    def start_processing_thread(self):
        if not self.processing_thread or not self.processing_thread.is_alive():
            self.processing_thread = Thread(target=self._process_queue, daemon=True)
            self.processing_thread.start()
            
    def _process_queue(self):
        while not self.stop_event.is_set():
            try:
                ruta, extension = self.process_queue.get(timeout=5)
                self._procesar_archivo_seguro(ruta, extension)
                self.process_queue.task_done()
            except:
                # Cola vacÃ­a, continuar
                import time
                time.sleep(0.1)
                
    def _procesar_archivo_seguro(self, ruta, extension):
        try:
            # Verificar recursos antes de procesar
            if not resource_monitor.can_process_file():
                logging.warning(f"[Carpeta {getattr(self, 'carpeta_numero', '?')}] âš ï¸ RECURSOS INSUFICIENTES para: {Path(ruta).name}")
                return
            
            resource_monitor.start_processing()
            
            mensaje = f"[Carpeta {getattr(self, 'carpeta_numero', '?')}] ðŸ”„ PROCESANDO: {Path(ruta).name}"
            logging.info(f"EQUIPO: {self.system_info['computer']} | USUARIO: {self.system_info['user']} | {mensaje}")
            if self.root:
                self.root.after(0, lambda: self._log_to_gui(mensaje))
            
            if ruta in self.archivos_procesando:
                return
                
            self.archivos_procesando.add(ruta)
            self._esperar_archivo_completo(ruta)
            
            if extension == '.zip':
                logging.info(f"[Carpeta {getattr(self, 'carpeta_numero', '?')}] ðŸ—ƒï¸ Procesando ZIP: {Path(ruta).name}")
                self.extraer_zip(ruta)
            elif extension in ['.txt', '.zpl']:
                logging.info(f"[Carpeta {getattr(self, 'carpeta_numero', '?')}] ðŸ“„ Procesando TXT/ZPL: {Path(ruta).name}")
                self.imprimir_txt(ruta)
            elif extension == '.pdf':
                mensaje = f"[Carpeta {getattr(self, 'carpeta_numero', '?')}] ðŸ“„ Procesando PDF: {Path(ruta).name}"
                logging.info(mensaje)
                if self.root:
                    self.root.after(0, lambda: self._log_to_gui(mensaje))
                self.procesar_pdf(ruta)
                
        except Exception as e:
            logging.exception(f"Error al procesar archivo {ruta}: {e}")
        finally:
            resource_monitor.finish_processing()
            self.archivos_procesando.discard(ruta)
            
    def _esperar_archivo_completo(self, ruta, max_intentos=20):
        import time
        import os
        
        # Ignorar archivos temporales comunes
        ruta_lower = ruta.lower()
        if any(temp in ruta_lower for temp in ['.tmp', '.temp', '.crdownload', '.part', '.download']):
            logging.info(f"Ignorando archivo temporal: {Path(ruta).name}")
            return False
        
        tamano_anterior = 0
        intentos_sin_cambio = 0
        
        for intento in range(max_intentos):
            try:
                if not Path(ruta).exists():
                    return False
                
                # Verificar tamaÃ±o del archivo
                tamano_actual = Path(ruta).stat().st_size
                
                # Si el tamaÃ±o no cambiÃ³ en 2 intentos consecutivos, probablemente estÃ© completo
                if tamano_actual == tamano_anterior and tamano_actual > 0:
                    intentos_sin_cambio += 1
                    if intentos_sin_cambio >= 2:
                        # Verificar acceso exclusivo (prueba definitiva)
                        try:
                            # Intentar abrir en modo exclusivo (Windows)
                            fd = os.open(ruta, os.O_RDWR | os.O_EXCL)
                            os.close(fd)
                            return True
                        except (PermissionError, OSError):
                            # Si falla, intentar abrir en modo lectura
                            with open(ruta, 'rb') as f:
                                f.read(1)
                            # Archivo legible pero no exclusivo, esperar un poco mÃ¡s
                            intentos_sin_cambio = 1
                else:
                    intentos_sin_cambio = 0
                    tamano_anterior = tamano_actual
                
                time.sleep(1)
                
            except (PermissionError, IOError, OSError):
                time.sleep(1)
                
        logging.warning(f"Archivo posiblemente en uso o incompleto: {ruta}")
        return False

    def on_created(self, event):
        if event.is_directory:
            return

        ruta = event.src_path
        extension = Path(ruta).suffix.lower()
        nombre_archivo = Path(ruta).name.lower()
        
        # Esperar un momento para que el archivo se complete
        import time
        time.sleep(0.5)
        
        # Verificar que el archivo existe antes de validaciones
        if not Path(ruta).exists():
            logging.warning(f"Archivo no encontrado durante detecciÃ³n: {ruta}")
            return
        
        # Validaciones de seguridad
        if not SecurityValidator.validate_path(ruta, self.config["entrada"]):
            logging.error(f"[Carpeta {getattr(self, 'carpeta_numero', '?')}] âš ï¸ RUTA INSEGURA: {Path(ruta).name}")
            security_logger.log_file_blocked(Path(ruta).name, "Ruta insegura", ruta)
            return
            
        if not SecurityValidator.validate_filename(Path(ruta).name):
            logging.error(f"[Carpeta {getattr(self, 'carpeta_numero', '?')}] âš ï¸ NOMBRE INSEGURO: {Path(ruta).name}")
            security_logger.log_file_blocked(Path(ruta).name, "Nombre de archivo inseguro", ruta)
            return
            
        if not SecurityValidator.validate_file_extension(Path(ruta).name):
            logging.error(f"[Carpeta {getattr(self, 'carpeta_numero', '?')}] âš ï¸ EXTENSIÃ“N NO PERMITIDA: {Path(ruta).name}")
            security_logger.log_file_blocked(Path(ruta).name, "ExtensiÃ³n no permitida", ruta)
            return
        
        # Log bÃ¡sico para debug
        mensaje = f"[Carpeta {getattr(self, 'carpeta_numero', '?')}] ðŸ” ARCHIVO DETECTADO: {Path(ruta).name} (ext: {extension})"
        logging.info(mensaje)
        if self.root:
            self.root.after(0, lambda: self._log_to_gui(mensaje))
        
        if extension not in ['.zip', '.txt', '.zpl', '.pdf']:
            return
            
        # Verificar que el archivo estÃ© dentro del directorio monitoreado
        try:
            ruta_canonica = Path(ruta).resolve()
            directorio_entrada = Path(self.config["entrada"]).resolve()
            
            if not str(ruta_canonica).startswith(str(directorio_entrada)):
                logging.error(f"Intento de acceso a archivo fuera del directorio monitoreado: {ruta}")
                return
        except Exception as e:
            logging.error(f"Error al verificar ruta canÃ³nica: {e}")
            return
        
        # Ignorar archivos de la carpeta de historial
        historial_dir = self.config.get("historial", "")
        if historial_dir and historial_dir in ruta:
            logging.info(f"Ignorando archivo de historial: {Path(ruta).name}")
            return
        
        # Ignorar archivos PDF con nombre Control
        if extension == '.pdf' and 'control' in nombre_archivo:
            logging.info(f"Ignorando PDF de control: {Path(ruta).name}")
            return
        
        # Ignorar archivos marcados para ignorar
        if ruta in self.ignorar_archivos:
            logging.info(f"Ignorando archivo marcado: {Path(ruta).name}")
            return
            
        # Ignorar archivos reciÃ©n extraÃ­dos de ZIP
        if ruta in self.archivos_extraidos:
            logging.info(f"Ignorando archivo extraido: {Path(ruta).name}")
            self.archivos_extraidos.discard(ruta)
            return
            
        # Evitar duplicados
        if ruta in self.archivos_procesando:
            logging.info(f"Archivo ya en procesamiento, ignorando: {Path(ruta).name}")
            return
            
        try:
            self.process_queue.put((ruta, extension), timeout=5)
            logging.info(f"[Carpeta {self.carpeta_numero}] Archivo agregado a la cola: {Path(ruta).name}")
        except Exception as e:
            logging.error(f"Error al agregar archivo a la cola: {e}")

    def extraer_zip(self, ruta_zip):
        zip_path = Path(ruta_zip)
        
        if not zip_path.exists():
            logging.warning(f"ðŸ“ Archivo ZIP no encontrado: {ruta_zip}")
            return False
            
        if not zip_path.is_file():
            logging.warning(f"ðŸ“ No es un archivo: {ruta_zip}")
            return False
            
        try:
            size_mb = zip_path.stat().st_size / (1024 * 1024)
            if size_mb > MAX_ZIP_SIZE_MB:
                logging.error(f"ðŸ“ Archivo ZIP demasiado grande: {size_mb:.1f}MB")
                return False
        except Exception as e:
            logging.error(f"Error al verificar tamaÃ±o del ZIP: {e}")
            return False
            
        carpeta_destino = self.config["entrada"]
        
        if not validar_directorio(carpeta_destino):
            logging.error(f"ðŸ“ Directorio no vÃ¡lido: {carpeta_destino}")
            return False
            
        try:
            # Detener observer completamente
            if self.observer:
                self.observer.stop()
                logging.info("Observer detenido para extracciÃ³n")
            
            # Validar contenido del ZIP antes de extraer
            import zipfile
            
            with zipfile.ZipFile(str(zip_path)) as zip_ref:
                # Verificar tamaÃ±o total descomprimido
                total_size = sum(info.file_size for info in zip_ref.infolist())
                if total_size > 100 * 1024 * 1024:  # 100MB
                    logging.error(f"ZIP demasiado grande al descomprimir: {total_size/(1024*1024):.1f}MB")
                    return False
                
                # Verificar archivos peligrosos
                archivos_seguros = []
                for info in zip_ref.infolist():
                    # Verificar path traversal
                    if info.filename.startswith('/') or '..' in info.filename:
                        logging.error(f"Archivo inseguro detectado: {info.filename}")
                        return False
                    
                    # Verificar extensiones permitidas
                    nombre = info.filename.lower()
                    if nombre.endswith(('.txt', '.zpl')):
                        archivos_seguros.append(info)
                
                # Extraer solo archivos seguros
                for info in archivos_seguros:
                    zip_ref.extract(info, carpeta_destino)
                    logging.info(f"Archivo extraÃ­do: {info.filename}")
                
            logging.info(f"ZIP procesado de forma segura: {zip_path.name}")
            
            import time
            time.sleep(1)
            
            # PRIMERO: Eliminar archivos no deseados
            archivos_txt = []
            for archivo in Path(carpeta_destino).iterdir():
                if archivo.is_file():
                    if archivo.suffix.lower() == '.txt':
                        archivos_txt.append(archivo)
                    elif archivo.suffix.lower() in ['.pdf', '.png', '.jpg']:
                        archivo.unlink()
                        logging.info(f"Eliminado archivo no deseado: {archivo.name}")
            
            # SEGUNDO: Procesar archivos TXT
            for archivo in archivos_txt:
                logging.info(f"Procesando TXT extraido: {archivo.name}")
                self.imprimir_txt(str(archivo))
            
            time.sleep(2)  # Esperar antes de reiniciar observer
            
            # Reiniciar observer (crear uno nuevo)
            if self.observer:
                try:
                    # Crear un nuevo observer en lugar de reiniciar el existente
                    from watchdog.observers import Observer
                    nuevo_observer = Observer()
                    nuevo_observer.schedule(self, path=self.config["entrada"], recursive=False)
                    nuevo_observer.start()
                    
                    # Actualizar la referencia
                    self.observer = nuevo_observer
                    logging.info("Nuevo observer iniciado")
                except Exception as e:
                    logging.error(f"Error al reiniciar observer: {e}")
            
            mover_a_historial(None, str(zip_path), None, None, self.config["historial"])
            return True
            
        except ReadError as e:
            logging.error(f"ðŸ“ Error al extraer ZIP: {e}")
            return False
        except Exception as e:
            logging.exception(f"ðŸ“ Error crÃ­tico al procesar ZIP: {e}")
            return False

    def imprimir_txt(self, ruta_txt):
        txt_path = Path(ruta_txt)
        
        if not txt_path.exists() or not txt_path.is_file():
            logging.warning(f"ðŸ“„ Archivo no vÃ¡lido: {ruta_txt}")
            return False
            
        try:
            size_kb = txt_path.stat().st_size / 1024
            if size_kb > MAX_TXT_SIZE_KB:
                logging.error(f"ðŸ“„ Archivo demasiado grande: {size_kb:.1f}KB")
                return False
        except Exception as e:
            logging.error(f"Error al verificar tamaÃ±o: {e}")
            return False
            
        try:
            contenido = None
            for encoding in ENCODINGS:
                try:
                    with open(txt_path, "r", encoding=encoding) as f:
                        contenido = f.read().strip()
                    break
                except UnicodeDecodeError:
                    continue
                    
            if not contenido:
                logging.warning(f"ðŸ“„ Archivo vacÃ­o o no decodificable: {ruta_txt}")
                return False
                
            # Sanitizar contenido ZPL
            contenido_sanitizado = ZPLSanitizer.sanitize_zpl_content(contenido)
            if not contenido_sanitizado:
                logging.error(f"ðŸ“„ ZPL no se pudo sanitizar: {txt_path.name}")
                return False
            
            # Validar estructura ZPL
            if not ZPLSanitizer.validate_zpl_structure(contenido_sanitizado):
                logging.error(f"ðŸ“„ Estructura ZPL invÃ¡lida: {txt_path.name}")
                return False
            
            # Usar contenido sanitizado
            contenido = contenido_sanitizado

            try:
                headers = LABELARY_HEADERS
                url = LABELARY_URL
                
                response = requests.post(url, data=contenido.encode("utf-8"), headers=headers, timeout=10)
                
                if response.status_code == 200:
                    # Mostrar vista previa
                    import sys
                    gui_path = Path(__file__).parent.parent / "gui"
                    sys.path.insert(0, str(gui_path))
                    from vista_previa import mostrar_vista_previa
                    
                    def callback_imprimir():
                        self._procesar_impression(str(txt_path), contenido)
                    
                    logging.info(f"[Carpeta {self.carpeta_numero}] Respuesta Labelary OK. Root disponible: {self.root is not None}")
                    
                    if self.root:
                        logging.info(f"[Carpeta {self.carpeta_numero}] âœ… MOSTRANDO VISTA PREVIA para: {Path(txt_path).name}")
                        self.root.after(0, lambda: mostrar_vista_previa(response.content, contenido, callback_imprimir))
                    else:
                        logging.warning(f"[Carpeta {self.carpeta_numero}] âš ï¸ SIN GUI - IMPRIMIENDO DIRECTAMENTE: {Path(txt_path).name}")
                        return self._procesar_impression(str(txt_path), contenido)
                    return True
                else:
                    return self._procesar_impression(str(txt_path), contenido)
                    
            except requests.exceptions.Timeout:
                logging.warning("ðŸ“„ Timeout en vista previa")
                return self._procesar_impression(str(txt_path), contenido)
            except Exception as e:
                logging.warning(f"ðŸ“„ Error en vista previa: {e}")
                return self._procesar_impression(str(txt_path), contenido)
                
        except Exception as e:
            logging.exception(f"ðŸ“„ Error crÃ­tico: {e}")
            return False

    def procesar_pdf(self, ruta_pdf):
        """Procesa PDF con o sin recorte segÃºn configuraciÃ³n"""
        pdf_path = Path(ruta_pdf)
        
        if not pdf_path.exists():
            logging.warning(f"PDF no encontrado: {ruta_pdf}")
            return False
        
        # Verificar configuraciÃ³n de recorte ANTES de procesar
        recortar_habilitado = self.config.get('recortar_pdf')
        if isinstance(recortar_habilitado, str):
            recortar_habilitado = recortar_habilitado.lower() == 'true'
        elif recortar_habilitado is None:
            recortar_habilitado = True
        
        logging.info(f"ConfiguraciÃ³n de recorte PDF: {recortar_habilitado} (carpeta: {self.config.get('entrada', 'N/A')})")
        
        if not recortar_habilitado:
            # Si no se debe recortar, imprimir PDF directamente
            logging.info("PDF se enviarÃ¡ sin recortar - imprimiendo directamente")
            return self._imprimir_pdf_directo(ruta_pdf)
            
        try:
            # Solo usar poppler si se va a recortar
            poppler_path = self.config.get("poppler", "")
            pdftoppm_exe = None
            
            # Buscar pdftoppm.exe
            posibles_rutas = [
                Path(poppler_path) / "pdftoppm.exe" if poppler_path else None,
                Path("poppler/poppler-23.08.0/Library/bin/pdftoppm.exe"),
                Path("C:/Herramientas/poppler/Library/bin/pdftoppm.exe"),
            ]
            
            for ruta in posibles_rutas:
                if ruta and ruta.exists():
                    pdftoppm_exe = str(ruta)
                    logging.info(f"Usando poppler para recorte: {pdftoppm_exe}")
                    break
                    
            if not pdftoppm_exe:
                logging.error("No se encontrÃ³ pdftoppm.exe para recorte")
                return False
                
            # Convertir a imagen de alta resoluciÃ³n
            temp_img = pdf_path.parent / f"{pdf_path.stem}_temp.png"
            
            cmd = [
                pdftoppm_exe,
                "-png", "-singlefile", "-r", "600",  # Doble resoluciÃ³n
                "-aa", "yes",  # Anti-aliasing
                "-aaVector", "yes",  # Anti-aliasing para vectores
                str(pdf_path),
                str(temp_img.with_suffix(""))
            ]
            
            # Ocultar la ventana de comando
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, startupinfo=startupinfo)
            
            if result.returncode != 0:
                logging.error(f"Error al convertir PDF: {result.stderr}")
                return False
                
            # Cargar imagen generada
            if temp_img.exists():
                img = Image.open(temp_img)
            else:
                logging.error("No se generÃ³ la imagen del PDF")
                return False
                
            # Recortar la imagen
            img_recortada = self._recortar_etiqueta(img)
            logging.info("PDF recortado automÃ¡ticamente")
            
            # Procesamiento directo sin vista previa
            self._finalizar_pdf(ruta_pdf, img_recortada, temp_img, None)
            
            return True
            
        except subprocess.TimeoutExpired:
            logging.error("Timeout al procesar PDF")
            return False
        except Exception as e:
            logging.exception(f"Error al procesar PDF: {e}")
            return False
            
    def _recortar_etiqueta(self, img):
        """Recorta automÃ¡ticamente la etiqueta del PDF"""
        try:
            # Convertir a escala de grises
            gray = img.convert('L')
            width, height = gray.size
            
            # Buscar contenido real (no blanco puro)
            pixels = list(gray.getdata())
            
            # Encontrar lÃ­mites del contenido no blanco
            min_x, min_y = width, height
            max_x, max_y = 0, 0
            
            for y in range(height):
                for x in range(width):
                    pixel = pixels[y * width + x]
                    if pixel < 250:  # No es blanco puro
                        min_x = min(min_x, x)
                        max_x = max(max_x, x)
                        min_y = min(min_y, y)
                        max_y = max(max_y, y)
            
            # Verificar si se encontrÃ³ contenido
            if min_x >= width or min_y >= height or max_x <= 0 or max_y <= 0:
                logging.warning("No se detectÃ³ contenido para recortar")
                return img
            
            # Agregar margen
            margin = 30
            left = max(0, min_x - margin)
            top = max(0, min_y - margin)
            right = min(width, max_x + margin)
            bottom = min(height, max_y + margin)
            
            # Recortar imagen
            logging.info(f"Aplicando recorte: ({left},{top},{right},{bottom})")
            img_recortada = img.crop((left, top, right, bottom))
            
            logging.info(f"PDF recortado: {img.size} -> {img_recortada.size} (contenido: {min_x},{min_y} a {max_x},{max_y})")
            
            # Verificar que realmente se recortÃ³
            if img_recortada.size == img.size:
                logging.error("ERROR: La imagen no se recortÃ³ correctamente")
            else:
                logging.info("Recorte aplicado exitosamente")
                
            return img_recortada
            
        except Exception as e:
            logging.exception(f"Error al recortar: {e}")
            return img
            
    def _finalizar_pdf(self, ruta_pdf, img_recortada, temp_img, impresora=None):
        """Finaliza el procesamiento del PDF"""
        try:
            # Guardar imagen recortada
            salida_dir = self.config.get("salida", self.config.get("entrada", "."))
            salida_path = Path(salida_dir) / f"{Path(ruta_pdf).stem}_recortada.png"
            img_recortada.save(salida_path, "PNG", dpi=(300, 300))
            
            logging.info(f"Imagen guardada: {salida_path}")
            
            # Imprimir imagen PNG con la impresora configurada para esta carpeta
            impresora_carpeta = self.config.get("impresora")
            logging.info(f"Intentando imprimir en impresora de carpeta: {impresora_carpeta}")
            if self._imprimir_png(salida_path, impresora_carpeta):
                logging.info("Imagen enviada a impresora exitosamente")
            else:
                logging.error("Fallo al enviar imagen a impresora")
            
            # Limpiar archivo temporal
            if temp_img.exists():
                temp_img.unlink()
                
            # Mover PDF a historial
            historial_dir = self.config.get("historial", self.config.get("entrada", "."))
            mover_a_historial(str(ruta_pdf), None, str(salida_path), None, historial_dir)
            
            return True
            
        except Exception as e:
            logging.exception(f"Error al finalizar PDF: {e}")
            return False
            
    def _imprimir_png(self, png_path, impresora=None):
        """Imprime imagen PNG usando la función especializada"""
        try:
            # Usar la impresora seleccionada o la configurada para esta carpeta específica
            impresora_a_usar = impresora if impresora else self.config.get("impresora")

            # Si no hay impresora, usar "IMPRESORA_NO_CONFIGURADA"
            if not impresora_a_usar:
                impresora_a_usar = "IMPRESORA_NO_CONFIGURADA"
                logging.warning(f"No hay impresora configurada para PNG: {Path(png_path).name}")

            # Obtener cantidad de copias
            copias = self.config.get('copias', 1)

            # Leer contenido del PNG como base64 para enviar a API
            try:
                import base64
                png_bytes = self._build_png_bytes_for_print(png_path)
                png_content = base64.b64encode(png_bytes).decode('utf-8')

                # SIEMPRE enviar a API primero
                api_sent = self._send_to_api_png(png_path, png_content, impresora_a_usar, copias)

                if api_sent:
                    logging.info(f"PNG enviado a API: {Path(png_path).name}")
                    return True
                else:
                    # Fallback a impresión directa
                    logging.info("API no disponible para PNG, usando impresión directa")

                    if impresora_a_usar == "IMPRESORA_NO_CONFIGURADA":
                        logging.error(f"No se puede imprimir PNG {Path(png_path).name}: impresora no configurada")
                        return False

                    fallback_path = self._create_temp_grayscale_png_if_needed(png_path)
                    try:
                        return imprimir_png(fallback_path, impresora_a_usar)
                    finally:
                        if fallback_path != str(png_path):
                            try:
                                Path(fallback_path).unlink(missing_ok=True)
                            except Exception:
                                pass

            except Exception as e:
                logging.error(f"Error procesando PNG: {e}")
                return False

        except Exception as e:
            logging.exception(f"Error al imprimir PNG: {e}")
            return False

    def _is_grayscale_forced(self):
        return bool(self.config.get("force_grayscale", False))

    def _build_png_bytes_for_print(self, png_path):
        if not self._is_grayscale_forced():
            with open(png_path, 'rb') as handle:
                return handle.read()

        with Image.open(png_path) as img:
            buffer = io.BytesIO()
            img.convert('L').save(buffer, format='PNG')
            logging.info(f"Forzando impresión B/N para PNG: {Path(png_path).name}")
            return buffer.getvalue()

    def _create_temp_grayscale_png_if_needed(self, png_path):
        if not self._is_grayscale_forced():
            return str(png_path)

        with Image.open(png_path) as img:
            temp_file = tempfile.NamedTemporaryFile(
                prefix=f"{Path(png_path).stem}_bn_",
                suffix=".png",
                delete=False,
            )
            temp_path = temp_file.name
            temp_file.close()
            img.convert('L').save(temp_path, format='PNG')
            return temp_path
    def _send_to_api_png(self, filename, png_content, printer, copies):
        """Enviar trabajo PNG a la API"""
        try:
            # Leer puerto de la API
            api_port = None
            try:
                with open('api_port.txt', 'r') as f:
                    api_port = f.read().strip()
            except:
                return False
            
            if not api_port:
                return False
            
            import requests
            data = {
                'filename': Path(filename).name,
                'content': f'PNG_BASE64:{png_content}',  # Marcar como PNG
                'printer': printer,
                'copies': copies
            }
            
            response = requests.post(
                f"http://localhost:{api_port}/api/process-file",
                json=data,
                timeout=10  # MÃ¡s tiempo para PNGs grandes
            )
            
            if response.status_code == 200:
                result = response.json()
                logging.info(f"PNG API Job ID: {result.get('job_id')}")
                return True
            else:
                logging.warning(f"PNG API error: {response.status_code}")
                return False
                
        except Exception as e:
            logging.warning(f"Error enviando PNG a API: {e}")
            return False
    
    def _imprimir_pdf_directo(self, ruta_pdf):
        """Imprime PDF directamente sin recorte"""
        try:
            # Usar la impresora configurada para esta carpeta especÃ­fica
            impresora = self.config.get("impresora")
            if not impresora:
                logging.error("No hay impresora configurada")
                return False
            
            # Mostrar vista previa simple y luego imprimir
            logging.info(f"Preparando PDF para impresiÃ³n directa: {ruta_pdf}")
            
            # Convertir PDF a imagen solo para vista previa (sin recorte)
            poppler_path = self.config.get("poppler", "")
            pdftoppm_exe = None
            
            # Buscar pdftoppm.exe
            posibles_rutas = [
                Path(poppler_path) / "pdftoppm.exe" if poppler_path else None,
                Path("C:\\Herramientas\\poppler\\Library\\bin\\pdftoppm.exe"),
                Path("poppler\\poppler-23.08.0\\Library\\bin\\pdftoppm.exe"),
            ]
            
            for ruta in posibles_rutas:
                if ruta and ruta.exists():
                    pdftoppm_exe = str(ruta)
                    break
            
            if pdftoppm_exe:
                # Convertir solo para vista previa
                temp_img = Path(ruta_pdf).parent / f"{Path(ruta_pdf).stem}_preview.png"
                
                cmd = [
                    pdftoppm_exe,
                    "-png", "-singlefile", "-r", "200",  # Mejor resoluciÃ³n para vista previa
                    "-aa", "yes",
                    str(ruta_pdf),
                    str(temp_img.with_suffix(""))
                ]
                
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, startupinfo=startupinfo)
                
                if result.returncode == 0 and temp_img.exists():
                    img = Image.open(temp_img)
                    
                    # Procesamiento directo sin vista previa
                    self._finalizar_pdf_directo(ruta_pdf, temp_img, impresora)
                    return True
            
            # Si no se puede hacer vista previa, imprimir directamente
            return self._finalizar_pdf_directo(ruta_pdf, None, impresora)
            
        except Exception as e:
            logging.exception(f"Error al procesar PDF directo: {e}")
            return False
    
    def _finalizar_pdf_directo(self, ruta_pdf, temp_img, impresora=None):
        """Finaliza la impresiÃ³n directa del PDF usando mÃ©todos compatibles con red"""
        try:
            impresora_a_usar = impresora if impresora else self.config.get("impresora")
            logging.info(f"Intentando imprimir PDF directamente en: {impresora_a_usar}")
            
            # Convertir PDF a imagen y usar el mÃ©todo PNG que ya funciona
            if not temp_img:
                # Si no hay imagen temporal, convertir ahora
                poppler_path = self.config.get("poppler", "")
                pdftoppm_exe = None
                
                posibles_rutas = [
                    Path(poppler_path) / "pdftoppm.exe" if poppler_path else None,
                    Path("poppler/poppler-23.08.0/Library/bin/pdftoppm.exe"),
                    Path("C:/Herramientas/poppler/Library/bin/pdftoppm.exe"),
                ]
                
                for ruta in posibles_rutas:
                    if ruta and ruta.exists():
                        pdftoppm_exe = str(ruta)
                        break
                
                if pdftoppm_exe:
                    temp_img = Path(ruta_pdf).parent / f"{Path(ruta_pdf).stem}_direct.png"
                    
                    cmd = [
                        pdftoppm_exe,
                        "-png", "-singlefile", "-r", "600",  # Doble resoluciÃ³n
                        "-aa", "yes",  # Anti-aliasing
                        "-aaVector", "yes",  # Anti-aliasing para vectores
                        str(ruta_pdf),
                        str(temp_img.with_suffix(""))
                    ]
                    
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, startupinfo=startupinfo)
                    
                    if result.returncode != 0 or not temp_img.exists():
                        logging.error("No se pudo convertir PDF a imagen")
                        return False
                else:
                    logging.error("No se encontrÃ³ poppler para conversiÃ³n")
                    return False
            
            # Obtener cantidad de copias
            copias = self.config.get('copias', 1)
            logging.info(f"Imprimiendo {copias} copia(s)")
            
            # Imprimir las copias necesarias
            success = True
            for i in range(copias):
                if not self._imprimir_png(str(temp_img), impresora_a_usar):
                    success = False
                    logging.error(f"Error al imprimir copia {i+1}")
                    break
                elif copias > 1:
                    logging.info(f"Copia {i+1} de {copias} enviada")
                    import time
                    time.sleep(1)  # Pausa entre copias
            
            # Limpiar archivo temporal
            if temp_img and Path(temp_img).exists():
                try:
                    Path(temp_img).unlink()
                except:
                    pass
            
            # Mover PDF a historial
            if success:
                historial_dir = self.config.get("historial", self.config.get("entrada", "."))
                mover_a_historial(str(ruta_pdf), None, None, None, historial_dir)
                logging.info("PDF procesado y movido a historial")
            
            return success
            
        except Exception as e:
            logging.exception(f"Error al finalizar PDF directo: {e}")
            return False

    def _procesar_impression(self, ruta_txt, contenido, impresora=None):
        try:
            # Usar la impresora seleccionada o la configurada para esta carpeta especÃ­fica
            impresora_a_usar = impresora if impresora else self.config.get("impresora")
            
            # Si no hay impresora, usar "IMPRESORA_NO_CONFIGURADA"
            if not impresora_a_usar:
                impresora_a_usar = "IMPRESORA_NO_CONFIGURADA"
                logging.warning(f"No hay impresora configurada para {Path(ruta_txt).name}")
            
            # Obtener cantidad de copias
            copias = self.config.get('copias', 1)
            
            # SIEMPRE enviar a API primero (incluso con impresora invÃ¡lida)
            api_sent = self._send_to_api(ruta_txt, contenido, impresora_a_usar, copias)
            
            if api_sent:
                logging.info(f"Trabajo enviado a API: {Path(ruta_txt).name}")
                # La API se encargarÃ¡ de manejar impresoras invÃ¡lidas
                success = True
            else:
                # Fallback a impresiÃ³n directa solo si API no estÃ¡ disponible
                logging.info("API no disponible, usando impresiÃ³n directa")
                
                # Validar impresora solo para impresiÃ³n directa
                if impresora_a_usar == "IMPRESORA_NO_CONFIGURADA":
                    logging.error(f"No se puede imprimir {Path(ruta_txt).name}: impresora no configurada")
                    return False
                
                success = imprimir_zpl_directo(contenido, impresora_a_usar, copias)
                
                if not success:
                    logging.error(f"Error al imprimir: {Path(ruta_txt).name}")
                    return False
            
            # Log del trabajo de impresiÃ³n con informaciÃ³n del sistema
            security_logger.log_print_job(Path(ruta_txt).name, impresora_a_usar, copias, success)
            logging.info(f"TRABAJO COMPLETADO - EQUIPO: {self.system_info['computer']} | USUARIO: {self.system_info['user']} | ARCHIVO: {Path(ruta_txt).name} | IMPRESORA: {impresora_a_usar} | COPIAS: {copias}")
            
            # Mover a historial
            historial_dir = self.config.get("historial")
            if not historial_dir or not Path(historial_dir).exists():
                Path(historial_dir).mkdir(parents=True, exist_ok=True)
                
            if mover_a_historial(None, ruta_txt, None, None, self.config["historial"]):
                logging.info(f"ARCHIVO FINALIZADO - EQUIPO: {self.system_info['computer']} | ARCHIVO: {Path(ruta_txt).name} | HISTORIAL: {self.config['historial']}")
                return True
            else:
                logging.warning(f"ERROR HISTORIAL - EQUIPO: {self.system_info['computer']} | ARCHIVO: {Path(ruta_txt).name}")
                return False
                
        except Exception as e:
            logging.exception(f"ðŸ–¨ï¸ Error crÃ­tico: {e}")
            return False
    
    def _send_to_api(self, filename, content, printer, copies):
        """Enviar trabajo a la API"""
        try:
            # Leer puerto de la API
            api_port = None
            try:
                with open('api_port.txt', 'r') as f:
                    api_port = f.read().strip()
            except:
                return False
            
            if not api_port:
                return False
            
            import requests
            data = {
                'filename': Path(filename).name,
                'content': content,
                'printer': printer,
                'copies': copies
            }
            
            response = requests.post(
                f"http://localhost:{api_port}/api/process-file",
                json=data,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                logging.info(f"API Job ID: {result.get('job_id')}")
                return True
            else:
                logging.warning(f"API error: {response.status_code}")
                return False
                
        except Exception as e:
            logging.warning(f"Error enviando a API: {e}")
            return False
            
    def shutdown(self):
        self.stop_event.set()
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5)
        logging.info("Handler cerrado correctamente")
