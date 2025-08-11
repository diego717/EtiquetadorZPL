"""
Instalador simple del servicio
"""

import subprocess
import sys
import os

def install_service_simple():
    """Instalar servicio de forma simple"""
    print("=== Instalador Simple Servicio ===")
    
    # Verificar pywin32
    try:
        import win32serviceutil
        print("pywin32 disponible")
    except ImportError:
        print("Instalando pywin32...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pywin32"])
        print("pywin32 instalado")
    
    # Instalar servicio
    try:
        print("Instalando servicio...")
        result = subprocess.run([
            sys.executable, "windows_service.py", "install"
        ], capture_output=True, text=True, shell=True)
        
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        print("Return code:", result.returncode)
        
        if result.returncode == 0:
            print("Servicio instalado")
            
            # Iniciar servicio
            print("Iniciando servicio...")
            start_result = subprocess.run([
                "net", "start", "EtiquetadorZPL"
            ], capture_output=True, text=True, shell=True)
            
            print("Start STDOUT:", start_result.stdout)
            print("Start STDERR:", start_result.stderr)
            
            if start_result.returncode == 0:
                print("Servicio iniciado correctamente")
            else:
                print("Error iniciando servicio")
        else:
            print("Error instalando servicio")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    install_service_simple()
    input("Presiona Enter...")