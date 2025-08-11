"""
Instalador automático de Poppler
"""

import os
import requests
import zipfile
from pathlib import Path
import shutil

def install_poppler():
    """Instalar Poppler automáticamente"""
    print("=== Instalando Poppler ===")
    
    # URL de descarga de Poppler para Windows
    poppler_url = "https://github.com/oschwartz10612/poppler-windows/releases/download/v23.08.0-0/Release-23.08.0-0.zip"
    
    # Directorio de instalación
    install_dir = Path("poppler")
    install_dir.mkdir(exist_ok=True)
    
    zip_file = install_dir / "poppler.zip"
    
    try:
        # Descargar Poppler
        print("Descargando Poppler...")
        response = requests.get(poppler_url, stream=True)
        response.raise_for_status()
        
        with open(zip_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print("Poppler descargado")
        
        # Extraer archivo
        print("Extrayendo archivos...")
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            zip_ref.extractall(install_dir)
        
        # Buscar el directorio bin
        bin_path = None
        for root, dirs, files in os.walk(install_dir):
            if 'pdftoppm.exe' in files:
                bin_path = Path(root)
                break
        
        if bin_path:
            print(f"Poppler instalado en: {bin_path}")
            
            # Crear archivo de configuración
            with open('poppler_path.txt', 'w') as f:
                f.write(str(bin_path))
            
            # Limpiar archivo zip
            zip_file.unlink()
            
            print("✅ Poppler instalado correctamente")
            return str(bin_path)
        else:
            print("❌ No se encontró pdftoppm.exe")
            return None
            
    except Exception as e:
        print(f"❌ Error instalando Poppler: {e}")
        return None

def test_poppler(poppler_path):
    """Probar instalación de Poppler"""
    try:
        pdftoppm_exe = Path(poppler_path) / "pdftoppm.exe"
        if pdftoppm_exe.exists():
            print(f"✅ Poppler funcional: {pdftoppm_exe}")
            return True
        else:
            print(f"❌ No se encontró: {pdftoppm_exe}")
            return False
    except Exception as e:
        print(f"❌ Error probando Poppler: {e}")
        return False

def main():
    """Función principal"""
    # Verificar si ya existe
    if Path('poppler_path.txt').exists():
        with open('poppler_path.txt', 'r') as f:
            existing_path = f.read().strip()
        
        if test_poppler(existing_path):
            print(f"Poppler ya está instalado: {existing_path}")
            return existing_path
    
    # Instalar Poppler
    poppler_path = install_poppler()
    
    if poppler_path and test_poppler(poppler_path):
        print("🎉 Poppler listo para usar")
        return poppler_path
    else:
        print("❌ Instalación de Poppler falló")
        return None

if __name__ == "__main__":
    result = main()
    input("Presiona Enter para continuar...")
    if result:
        print(f"Ruta de Poppler: {result}")
    else:
        print("Poppler no se pudo instalar")