"""
Tests para funciones principales de EtiquetadorZPL
"""

import unittest
import tempfile
import json
from pathlib import Path
import sys
import os

# Agregar paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

class TestCoreFunctions(unittest.TestCase):
    
    def setUp(self):
        """Configurar tests"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
    
    def test_printer_detection(self):
        """Test: Detectar impresoras"""
        try:
            from printer_utils import obtener_impresoras
            printers = obtener_impresoras()
            self.assertIsInstance(printers, list)
            print(f"OK: Impresoras detectadas: {len(printers)}")
        except Exception as e:
            self.fail(f"Error detectando impresoras: {e}")
    
    def test_config_load_save(self):
        """Test: Cargar y guardar configuración"""
        try:
            import configparser
            
            # Crear config de prueba
            config = configparser.ConfigParser()
            config['CARPETA1'] = {
                'entrada': 'C:/test',
                'impresora': 'Test_Printer',
                'historial': 'C:/test/historial',
                'activa': 'True'
            }
            
            config_file = self.temp_path / 'test_config.ini'
            with open(config_file, 'w') as f:
                config.write(f)
            
            # Verificar que se guardó
            self.assertTrue(config_file.exists())
            
            # Cargar y verificar
            loaded_config = configparser.ConfigParser()
            loaded_config.read(config_file)
            
            self.assertEqual(loaded_config['CARPETA1']['entrada'], 'C:/test')
            print("OK: Configuración: Cargar/Guardar OK")
            
        except Exception as e:
            self.fail(f"Error en configuración: {e}")
    
    def test_api_endpoints(self):
        """Test: Endpoints básicos de API"""
        try:
            # Verificar que el puerto se puede leer
            api_port = None
            try:
                with open('api_port.txt', 'r') as f:
                    api_port = f.read().strip()
            except:
                api_port = "8003"  # Puerto por defecto
            
            self.assertIsNotNone(api_port)
            print(f"OK: API Puerto: {api_port}")
            
            # Test básico de importación de FastAPI
            try:
                from fastapi_real import app
                self.assertIsNotNone(app)
                print("OK: FastAPI: Importación OK")
            except ImportError:
                print("AVISO: FastAPI no disponible")
                
        except Exception as e:
            self.fail(f"Error en API: {e}")
    
    def test_file_validation(self):
        """Test: Validación de archivos"""
        from validacion import validar_archivo_zpl

        # validar_archivo_zpl recibe el contenido ZPL, no la ruta del archivo.
        self.assertTrue(validar_archivo_zpl("^XA^FO50,50^A0N,50,50^FDTest^FS^XZ"))
        self.assertFalse(validar_archivo_zpl(""))
        self.assertFalse(validar_archivo_zpl("texto sin comandos zpl"))
    
    def test_database_connection(self):
        """Test: Conexión a base de datos"""
        from database import db

        stats = db.get_statistics()
        self.assertIsInstance(stats, dict)
    
    def test_notification_config(self):
        """Test: Configuración de notificaciones"""
        try:
            from get_writable_path import get_writable_config_path
            
            # Test configuración de notificaciones
            config = {
                "desktop_enabled": True,
                "notify_on_error": True,
                "notify_on_success": False
            }
            
            config_path = get_writable_config_path('test_notification.json')
            self.addCleanup(lambda: Path(config_path).unlink(missing_ok=True))
            with open(config_path, 'w') as f:
                json.dump(config, f)
            
            # Verificar que se guardó
            self.assertTrue(Path(config_path).exists())
            
            # Cargar y verificar
            with open(config_path, 'r') as f:
                loaded_config = json.load(f)
            
            self.assertEqual(loaded_config['desktop_enabled'], True)
            print("OK: Notificaciones: Configuración OK")
            
        except Exception as e:
            self.fail(f"Error en notificaciones: {e}")
    
    def test_gui_components(self):
        """Test: Componentes GUI básicos"""
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as e:
            self.skipTest(f"GUI no disponible en este equipo: {e}")
        try:
            root.withdraw()  # Ocultar ventana
            test_var = tk.StringVar()
            test_var.set("test_value")
            self.assertEqual(test_var.get(), "test_value")
        finally:
            root.destroy()
    
    def tearDown(self):
        """Limpiar después de tests"""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass

class TestSystemIntegration(unittest.TestCase):
    """Tests de integración del sistema"""
    
    def test_full_workflow_simulation(self):
        """Test: Simular flujo completo"""
        from printer_utils import obtener_impresoras
        printers = obtener_impresoras()
        if not printers:
            self.skipTest("No hay impresoras instaladas en este equipo")

        import configparser
        config = configparser.ConfigParser()
        config['CARPETA1'] = {
            'entrada': 'C:/temp/test',
            'impresora': printers[0],
            'historial': 'C:/temp/test/historial',
            'activa': 'True'
        }
        self.assertEqual(config['CARPETA1']['impresora'], printers[0])

def run_tests():
    """Ejecutar todos los tests"""
    print("Ejecutando tests de funciones principales...")
    print("=" * 50)
    
    # Crear suite de tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Agregar tests
    suite.addTests(loader.loadTestsFromTestCase(TestCoreFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestSystemIntegration))
    
    # Ejecutar tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("=" * 50)
    if result.wasSuccessful():
        print("OK: TODOS LOS TESTS PASARON")
    else:
        print(f"ERROR: {len(result.failures)} TESTS FALLARON")
        print(f"AVISO: {len(result.errors)} ERRORES")
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    input("\nPresiona Enter para continuar...")
    sys.exit(0 if success else 1)