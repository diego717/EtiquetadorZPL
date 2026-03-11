"""
Script de prueba para verificar selección de impresoras
"""

import sys
from pathlib import Path

# Agregar paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "gui"))

from printer_utils import obtener_impresoras

def test_printer_selection():
    """Probar selección de impresoras"""
    
    print("=== Test de Selección de Impresoras ===\n")
    
    # Obtener impresoras
    printers = obtener_impresoras()
    print(f"Impresoras encontradas: {len(printers)}")
    for i, printer in enumerate(printers):
        print(f"  {i+1}. {printer}")
    
    print("\n=== Simulando configuración de carpetas ===")
    
    # Simular configuración de 2 carpetas
    carpetas_config = []
    
    for i in range(2):
        print(f"\nCarpeta {i+1}:")
        print(f"  Impresoras disponibles: {len(printers)}")
        
        if i == 0:
            # Primera carpeta - usar primera impresora
            selected = printers[0] if printers else "Sin impresoras"
        else:
            # Segunda carpeta - usar segunda impresora si existe
            selected = printers[1] if len(printers) > 1 else printers[0] if printers else "Sin impresoras"
        
        carpeta_config = {
            'entrada': f'C:/Test/Carpeta{i+1}',
            'impresora': selected,
            'historial': f'C:/Test/Historial{i+1}',
            'copias': 1
        }
        
        carpetas_config.append(carpeta_config)
        print(f"  Configuración: {carpeta_config}")
    
    print("\n=== Verificando configuración final ===")
    for i, config in enumerate(carpetas_config):
        print(f"Carpeta {i+1}: {config['entrada']} -> {config['impresora']}")
    
    # Verificar que son diferentes si hay múltiples impresoras
    if len(printers) > 1:
        if carpetas_config[0]['impresora'] != carpetas_config[1]['impresora']:
            print("\n✅ CORRECTO: Las carpetas tienen impresoras diferentes")
        else:
            print("\n❌ ERROR: Las carpetas tienen la misma impresora")
    else:
        print("\n⚠️ Solo hay una impresora disponible")

if __name__ == "__main__":
    test_printer_selection()
    input("\nPresiona Enter para continuar...")