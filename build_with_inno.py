"""
Script para construir instalador con Inno Setup
"""

import subprocess
import sys
import os
from pathlib import Path

def check_inno_setup():
    """Verificar si Inno Setup está instalado"""
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe"
    ]
    
    for path in inno_paths:
        if Path(path).exists():
            return path
    
    return None

def create_icon_first():
    """Crear icono si no existe"""
    if not Path('etiquetador_icon.ico').exists():
        print("0. Creando icono...")
        try:
            exec(open('create_icon.py').read())
            print("OK: Icono creado")
        except Exception as e:
            print(f"AVISO: No se pudo crear icono: {e}")

def build_executable_first():
    """Construir ejecutable con PyInstaller primero"""
    print("1. Construyendo ejecutable con PyInstaller...")
    
    try:
        # Instalar PyInstaller si no está
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        
        # Comando PyInstaller optimizado
        cmd = [
            "pyinstaller",
            "--clean",
            "--noconfirm",
            "EtiquetadorZPL_Complete.spec"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("OK: Ejecutable creado: dist/EtiquetadorZPL.exe")
            return True
        else:
            print("ERROR: Error creando ejecutable:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def build_installer():
    """Construir instalador con Inno Setup"""
    print("2. Construyendo instalador con Inno Setup...")
    
    # Verificar Inno Setup
    iscc_path = check_inno_setup()
    if not iscc_path:
        print("ERROR: Inno Setup no encontrado")
        print("Descarga e instala desde: https://jrsoftware.org/isinfo.php")
        return False
    
    print(f"OK: Inno Setup encontrado: {iscc_path}")
    
    # Verificar que existe el ejecutable
    if not Path("dist/EtiquetadorZPL.exe").exists():
        print("ERROR: No se encontro dist/EtiquetadorZPL.exe")
        return False
    
    # Construir instalador
    try:
        cmd = [iscc_path, "EtiquetadorZPL_Simple.iss"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("OK: Instalador creado exitosamente")
            
            # Buscar archivo de salida
            installer_path = Path("installer/EtiquetadorZPL_Setup.exe")
            if installer_path.exists():
                size_mb = installer_path.stat().st_size / (1024 * 1024)
                print(f"Instalador: {installer_path} ({size_mb:.1f} MB)")
                return True
            else:
                print("AVISO: Instalador creado pero no encontrado en ubicacion esperada")
                return True
        else:
            print("ERROR: Error creando instalador:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"ERROR: Error ejecutando Inno Setup: {e}")
        return False

def create_build_info():
    """Crear información de build"""
    build_info = f"""
=== EtiquetadorZPL - Informacion de Build ===

Fecha: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Version: 1.0

Archivos generados:
- dist/EtiquetadorZPL.exe (Ejecutable principal)
- installer/EtiquetadorZPL_Setup.exe (Instalador)

Caracteristicas del instalador:
- Instalacion automatica
- Creacion de accesos directos
- Configuracion de carpetas de trabajo
- Inicio automatico (opcional)
- Desinstalador incluido
- Registro en Windows

Para distribuir:
1. Enviar archivo: installer/EtiquetadorZPL_Setup.exe
2. Usuario ejecuta el instalador
3. Seguir asistente de instalacion

Tamano aproximado: 40-60 MB
Requisitos: Windows 10/11 (64-bit)
"""
    
    with open("BUILD_INFO.txt", "w", encoding="utf-8") as f:
        f.write(build_info)
    
    print("INFO: Informacion de build guardada: BUILD_INFO.txt")

def main():
    """Función principal"""
    print("=== Constructor de Instalador EtiquetadorZPL ===")
    print("Usando: PyInstaller + Inno Setup")
    print()
    
    # Paso 0: Crear icono
    create_icon_first()
    
    # Paso 1: Construir ejecutable
    if not build_executable_first():
        print("ERROR: Fallo la construccion del ejecutable")
        return False
    
    print()
    
    # Paso 2: Construir instalador
    if not build_installer():
        print("ERROR: Fallo la construccion del instalador")
        return False
    
    print()
    
    # Paso 3: Crear información
    create_build_info()
    
    print()
    print("EXITO: Proceso completado exitosamente!")
    print()
    print("Archivos listos para distribucion:")
    print("   - installer/EtiquetadorZPL_Setup.exe")
    print()
    print("Para distribuir:")
    print("   1. Envia el archivo EtiquetadorZPL_Setup.exe")
    print("   2. El usuario lo ejecuta como administrador")
    print("   3. Sigue el asistente de instalacion")
    
    return True

if __name__ == "__main__":
    success = main()
    input("\nPresiona Enter para continuar...")
    
    if success:
        # Abrir carpeta de salida
        try:
            os.startfile("installer")
        except:
            pass