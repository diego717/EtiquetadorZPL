"""
Servicio de Windows para EtiquetadorZPL
"""

import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import os
import time
import threading
from pathlib import Path

class EtiquetadorService(win32serviceutil.ServiceFramework):
    _svc_name_ = "EtiquetadorZPL"
    _svc_display_name_ = "EtiquetadorZPL Service"
    _svc_description_ = "Servicio de procesamiento automático de etiquetas ZPL"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        
        # Cambiar al directorio del servicio
        service_dir = Path(__file__).parent
        os.chdir(service_dir)
    
    def SvcStop(self):
        """Detener servicio"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.running = False
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                            servicemanager.PYS_SERVICE_STOPPED,
                            (self._svc_name_, ''))
    
    def SvcDoRun(self):
        """Ejecutar servicio"""
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                            servicemanager.PYS_SERVICE_STARTED,
                            (self._svc_name_, ''))
        
        # Iniciar API en hilo separado
        api_thread = threading.Thread(target=self.start_api, daemon=True)
        api_thread.start()
        
        # Iniciar procesamiento de archivos
        processing_thread = threading.Thread(target=self.start_file_processing, daemon=True)
        processing_thread.start()
        
        # Esperar señal de parada
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
    
    def start_api(self):
        """Iniciar API"""
        try:
            from fast_api import start_fast_api
            start_fast_api()
        except Exception as e:
            servicemanager.LogErrorMsg(f"Error iniciando API: {e}")
    
    def start_file_processing(self):
        """Iniciar procesamiento de archivos"""
        try:
            # Cargar configuración
            import configparser
            config = configparser.ConfigParser()
            config.read('config.ini')
            
            # Iniciar monitoreo de carpetas
            from watchdog.observers import Observer
            from handlers import PDFHandler
            
            observer = Observer()
            
            # Agregar carpetas configuradas
            for section in config.sections():
                if section.startswith('CARPETA'):
                    carpeta_config = dict(config[section])
                    if carpeta_config.get('entrada'):
                        handler = PDFHandler(carpeta_config, observer)
                        observer.schedule(handler, carpeta_config['entrada'], recursive=False)
            
            observer.start()
            
            # Mantener servicio activo
            while self.running:
                time.sleep(1)
            
            observer.stop()
            observer.join()
            
        except Exception as e:
            servicemanager.LogErrorMsg(f"Error en procesamiento: {e}")

def install_service():
    """Instalar servicio"""
    try:
        win32serviceutil.InstallService(
            EtiquetadorService._svc_reg_class_,
            EtiquetadorService._svc_name_,
            EtiquetadorService._svc_display_name_,
            description=EtiquetadorService._svc_description_
        )
        print("Servicio instalado correctamente")
        return True
    except Exception as e:
        print(f"Error instalando servicio: {e}")
        return False

def uninstall_service():
    """Desinstalar servicio"""
    try:
        win32serviceutil.RemoveService(EtiquetadorService._svc_name_)
        print("Servicio desinstalado correctamente")
        return True
    except Exception as e:
        print(f"Error desinstalando servicio: {e}")
        return False

def start_service():
    """Iniciar servicio"""
    try:
        win32serviceutil.StartService(EtiquetadorService._svc_name_)
        print("Servicio iniciado")
        return True
    except Exception as e:
        print(f"Error iniciando servicio: {e}")
        return False

def stop_service():
    """Detener servicio"""
    try:
        win32serviceutil.StopService(EtiquetadorService._svc_name_)
        print("Servicio detenido")
        return True
    except Exception as e:
        print(f"Error deteniendo servicio: {e}")
        return False

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(EtiquetadorService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(EtiquetadorService)