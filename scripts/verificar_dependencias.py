"""
Script para verificar que todas las dependencias necesarias estén instaladas
y funcionando correctamente antes de crear el ejecutable.
"""

import sys
import importlib
import os
from pathlib import Path

# Lista de módulos requeridos
MODULOS_REQUERIDOS = [
    "tkinter",
    "PIL.Image",  # Pillow
    "watchdog",
    "requests",
    "win32print",  # parte de pywin32
    "win32api",    # parte de pywin32
    "sv_ttk",
    "psutil"       # para monitoreo de recursos
]

# Mapeo de módulos a paquetes pip
MODULO_A_PAQUETE = {
    "PIL.Image": "pillow",
    "win32print": "pywin32",
    "win32api": "pywin32"
}

# Lista de archivos críticos
ARCHIVOS_CRITICOS = [
    "launcher.pyw",
    "main_gui.py",
    "main_gui_optimized.py",
    "performance_optimizer.py",
    "main.py",
    "handlers.py",
    "printer.py",
    "pdf_printer.py",
    "config.py",
    "validacion.py",
    "printer_utils.py"
]

def verificar_modulos():
    """Verifica que todos los módulos requeridos estén instalados."""
    print("Verificando módulos requeridos...")
    modulos_faltantes = []
    
    for modulo in MODULOS_REQUERIDOS:
        try:
            importlib.import_module(modulo)
            print(f"[OK] {modulo}")
        except ImportError:
            print(f"[ERROR] {modulo} - No instalado")
            modulos_faltantes.append(modulo)
    
    return modulos_faltantes

def verificar_archivos():
    """Verifica que todos los archivos críticos existan."""
    print("\nVerificando archivos críticos...")
    archivos_faltantes = []
    
    for archivo in ARCHIVOS_CRITICOS:
        if Path(archivo).exists():
            print(f"[OK] {archivo}")
        else:
            print(f"[ERROR] {archivo} - No encontrado")
            archivos_faltantes.append(archivo)
    
    return archivos_faltantes

def verificar_poppler():
    """Verifica que Poppler esté disponible."""
    print("\nVerificando Poppler...")
    
    poppler_paths = [
        Path("poppler/poppler-23.08.0/Library/bin/pdftoppm.exe"),
        Path("C:/Herramientas/poppler/Library/bin/pdftoppm.exe")
    ]
    
    for path in poppler_paths:
        if path.exists():
            print(f"[OK] Poppler encontrado en: {path}")
            return True
    
    print("[ERROR] Poppler no encontrado")
    return False

def main():
    """Función principal."""
    print("=== VERIFICACIÓN DE DEPENDENCIAS ===\n")
    
    # Verificar módulos
    modulos_faltantes = verificar_modulos()
    
    # Verificar archivos
    archivos_faltantes = verificar_archivos()
    
    # Verificar Poppler
    poppler_ok = verificar_poppler()
    
    # Resumen
    print("\n=== RESUMEN ===")
    if not modulos_faltantes and not archivos_faltantes and poppler_ok:
        print("[OK] Todo listo para crear el ejecutable!")
    else:
        print("[ERROR] Se encontraron problemas:")
        
        if modulos_faltantes:
            # Convertir nombres de módulos a nombres de paquetes
            paquetes_faltantes = []
            for modulo in modulos_faltantes:
                paquete = MODULO_A_PAQUETE.get(modulo, modulo)
                if paquete not in paquetes_faltantes:  # Evitar duplicados (ej. pywin32)
                    paquetes_faltantes.append(paquete)
            
            print(f"- Módulos faltantes: {', '.join(modulos_faltantes)}")
            print("  Instala los paquetes con: pip install " + " ".join(paquetes_faltantes))
        
        if archivos_faltantes:
            print(f"- Archivos faltantes: {', '.join(archivos_faltantes)}")
        
        if not poppler_ok:
            print("- Poppler no encontrado. Asegúrate de tener la carpeta poppler con los binarios.")
    
    input("\nPresiona Enter para salir...")

if __name__ == "__main__":
    main()