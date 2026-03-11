"""
Script rápido para ejecutar tests principales
"""

import sys
from pathlib import Path

# Agregar paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "tests"))

def quick_test():
    """Test rápido de funciones críticas"""
    print("🚀 Test Rápido - Funciones Críticas")
    print("-" * 40)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Impresoras
    tests_total += 1
    try:
        sys.path.insert(0, str(project_root / "src"))
        from printer_utils import obtener_impresoras
        printers = obtener_impresoras()
        print(f"✅ Impresoras: {len(printers)} detectadas")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Impresoras: {e}")
    
    # Test 2: FastAPI
    tests_total += 1
    try:
        from api.fastapi_real import app
        print("✅ FastAPI: Importación OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ FastAPI: {e}")
    
    # Test 3: GUI
    tests_total += 1
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        print("✅ GUI: Tkinter OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ GUI: {e}")
    
    # Test 4: Configuración
    tests_total += 1
    try:
        from get_writable_path import get_writable_config_path
        test_path = get_writable_config_path('test.json')
        print("✅ Config: Rutas escribibles OK")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Config: {e}")
    
    # Test 5: Base de datos
    tests_total += 1
    try:
        from src.database import db
        stats = db.get_statistics()
        print("✅ Database: Conexión OK")
        tests_passed += 1
    except Exception as e:
        print(f"⚠️ Database: {e}")
    
    print("-" * 40)
    print(f"Resultado: {tests_passed}/{tests_total} tests pasaron")
    
    if tests_passed >= 3:  # Al menos 3 de 5 críticos
        print("✅ SISTEMA FUNCIONAL")
        return True
    else:
        print("❌ SISTEMA CON PROBLEMAS")
        return False

if __name__ == "__main__":
    success = quick_test()
    input("\nPresiona Enter para continuar...")
    sys.exit(0 if success else 1)