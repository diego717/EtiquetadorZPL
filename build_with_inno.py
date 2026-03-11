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
            if Path('etiquetador_icon.ico').exists():
                print("OK: Icono creado")
                # Habilitar icono en Inno Setup
                with open('EtiquetadorZPL_Simple.iss', 'r') as f:
                    content = f.read()
                content = content.replace('; SetupIconFile=etiquetador_icon.ico', 'SetupIconFile=etiquetador_icon.ico')
                with open('EtiquetadorZPL_Simple.iss', 'w') as f:
                    f.write(content)
            else:
                print("AVISO: No se pudo crear icono")
        except Exception as e:
            print(f"AVISO: No se pudo crear icono: {e}")

def build_executable_first():
    """Construir ejecutable con PyInstaller primero"""
    print("1. Construyendo ejecutable con PyInstaller...")
    
    # Verificar que existe el spec file
    if not Path("EtiquetadorZPL_Complete.spec").exists():
        print("ERROR: No se encontro EtiquetadorZPL_Complete.spec")
        return False
    
    # Verificar que existe el launcher
    if not Path("launcher_modern.py").exists():
        print("ERROR: No se encontro launcher_modern.py")
        return False
    
    try:
        # Instalar PyInstaller si no está
        print("Verificando PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], 
                      capture_output=True, check=True)
        
        # Limpiar build anterior
        import shutil
        for dir_name in ['build', 'dist']:
            if Path(dir_name).exists():
                shutil.rmtree(dir_name)
                print(f"Limpiado: {dir_name}/")
        
        # Comando PyInstaller optimizado
        cmd = [
            "pyinstaller",
            "--clean",
            "--noconfirm",
            "EtiquetadorZPL_Complete.spec"
        ]
        
        print("Ejecutando PyInstaller...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            if Path("dist/EtiquetadorZPL.exe").exists():
                size_mb = Path("dist/EtiquetadorZPL.exe").stat().st_size / (1024 * 1024)
                print(f"OK: Ejecutable creado: dist/EtiquetadorZPL.exe ({size_mb:.1f} MB)")
                return True
            else:
                print("ERROR: PyInstaller termino pero no se creo el ejecutable")
                return False
        else:
            print("ERROR: Error creando ejecutable:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def build_installer():
    """Construir instalador con Inno Setup"""
    print("3. Construyendo instalador con Inno Setup...")
    
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

def verify_before_build():
    """Verificar paths antes del build"""
    print("0. Verificando paths y archivos...")
    try:
        from verify_paths import verify_paths
        if not verify_paths():
            print("ERROR: Faltan archivos críticos")
            return False
        print("OK: Todos los archivos verificados")
        return True
    except Exception as e:
        print(f"AVISO: No se pudo ejecutar verificación: {e}")
        return True  # Continuar si no se puede verificar

def main():
    """Función principal"""
    print("=== Constructor de Instalador EtiquetadorZPL ===")
    print("Usando: PyInstaller + Inno Setup")
    print()
    
    # Paso 0: Verificar paths
    if not verify_before_build():
        return False
    
    print()
    
    # Paso 1: Crear icono
    create_icon_first()
    
    # Paso 2: Construir ejecutable
    if not build_executable_first():
        print("ERROR: Fallo la construccion del ejecutable")
        return False
    
    print()
    
    # Paso 3: Construir instalador
    if not build_installer():
        print("ERROR: Fallo la construccion del instalador")
        return False
    
    print()
    
    # Paso 4: Crear información
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