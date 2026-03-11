import os
import logging
import win32print
import win32ui
import win32con
import win32gui
from PIL import Image
import tempfile

def imprimir_png_alternativo(ruta_png, impresora=None):
    """Método alternativo para imprimir PNG usando shell"""
    try:
        import subprocess
        import tempfile
        import shutil
        
        if not impresora:
            impresora = win32print.GetDefaultPrinter()
        
        # Copiar el archivo a una ubicación temporal local si está en red
        local_png = ruta_png
        if ruta_png.startswith("\\\\") or ruta_png.startswith("//"):
            temp_dir = tempfile.gettempdir()
            local_png = os.path.join(temp_dir, "temp_print_image.png")
            shutil.copy2(ruta_png, local_png)
            logging.info(f"Copiado archivo de red a ubicación local: {local_png}")
        
        # Crear archivo temporal para comando
        bat_file = tempfile.mktemp(suffix=".bat")
        with open(bat_file, "w") as f:
            f.write(f'@echo off\n')
            f.write(f'echo Imprimiendo en {impresora}...\n')
            f.write(f'mspaint /pt "{local_png}" "{impresora}"\n')
        
        # Ejecutar comando
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        
        subprocess.run(bat_file, startupinfo=startupinfo)
        
        # Eliminar archivo temporal
        try:
            os.unlink(bat_file)
        except:
            pass
            
        logging.info(f"PNG impreso usando método alternativo en: {impresora}")
        return True
        
    except Exception as e:
        logging.exception(f"Error al imprimir PNG (método alternativo): {e}")
        return False

def imprimir_png(ruta_png, impresora=None):
    """Imprime PNG directamente sin márgenes usando win32ui"""
    try:
        ruta_png = str(ruta_png)
        
        if not os.path.exists(ruta_png):
            logging.error(f"Archivo no encontrado: {ruta_png}")
            return False
            
        if not impresora:
            impresora = win32print.GetDefaultPrinter()
        
        # Detectar si estamos ejecutando desde una unidad de red
        ejecutando_desde_red = False
        ruta_actual = os.path.abspath(__file__)
        if ruta_actual.startswith("\\\\") or ruta_actual.startswith("//") or \
           (len(ruta_actual) >= 2 and ruta_actual[0].isalpha() and ruta_actual[1] == ":" and \
            os.path.exists(f"\\\\{ruta_actual[0]}$")):
            ejecutando_desde_red = True
            logging.info(f"Detectado: Ejecutando desde unidad de red. Usando método alternativo.")
            
        # Intentar método alternativo si la impresora está en red o estamos ejecutando desde red
        if ejecutando_desde_red or "\\\\" in impresora or "//" in impresora:
            logging.info(f"Usando método alternativo para impresión.")
            return imprimir_png_alternativo(ruta_png, impresora)
        
        # Crear contexto de impresión
        try:
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(impresora)
        except Exception as e:
            logging.warning(f"Error al crear DC para {impresora}: {e}. Intentando método alternativo.")
            return imprimir_png_alternativo(ruta_png, impresora)
        
        try:
            # Iniciar documento
            hdc.StartDoc("Etiqueta PNG")
            hdc.StartPage()
            
            # Obtener dimensiones de la página
            page_width = hdc.GetDeviceCaps(win32con.HORZRES)
            page_height = hdc.GetDeviceCaps(win32con.VERTRES)
            
            # Cargar imagen
            img = Image.open(ruta_png)
            img_width, img_height = img.size
            
            # Antes de crear el bitmap para imprimir:
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            # Convertir a bitmap
            tmp_file = tempfile.mktemp(suffix=".bmp")
            img.save(tmp_file, "BMP")
            
            mem_dc = None
            hbmp = None
            try:
                # Cargar bitmap
                hbmp = win32gui.LoadImage(0, tmp_file, win32con.IMAGE_BITMAP, 0, 0, win32con.LR_LOADFROMFILE)
                if not hbmp:
                    raise RuntimeError("No se pudo cargar el bitmap para impresión.")
                bmp = win32ui.CreateBitmapFromHandle(hbmp)
                
                # Crear DC compatible
                mem_dc = hdc.CreateCompatibleDC()
                mem_dc.SelectObject(bmp)
                
                # Copiar bitmap a toda la página (sin márgenes)
                hdc.StretchBlt(
                    (0, 0), (page_width, page_height),
                    mem_dc, (0, 0), (img_width, img_height),
                    win32con.SRCCOPY
                )
            finally:
                # Limpiar recursos GDI
                if mem_dc:
                    try:
                        mem_dc.DeleteDC()
                    except Exception:
                        pass
                if hbmp:
                    try:
                        win32gui.DeleteObject(hbmp)
                    except Exception:
                        pass
                try:
                    os.unlink(tmp_file)
                except Exception:
                    pass
            
            # Finalizar
            hdc.EndPage()
            hdc.EndDoc()
            
            logging.info(f"PNG impreso sin márgenes en: {impresora}")
            return True
            
        finally:
            hdc.DeleteDC()
                
    except Exception as e:
        logging.exception(f"Error al imprimir PNG: {e}")
        return False