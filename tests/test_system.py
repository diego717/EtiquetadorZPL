"""
Tests del sistema EtiquetadorZPL
"""

import requests
import time
import json
import tempfile
from pathlib import Path

class SystemTester:
    def __init__(self, base_url="http://localhost:8002"):
        self.base_url = base_url
        self.session_id = None
        self.results = []
    
    def test(self, name, func):
        """Ejecutar test"""
        try:
            print(f"🧪 {name}... ", end="")
            result = func()
            if result:
                print("✅ PASS")
                self.results.append((name, "PASS", None))
            else:
                print("❌ FAIL")
                self.results.append((name, "FAIL", "Test returned False"))
        except Exception as e:
            print(f"❌ ERROR: {e}")
            self.results.append((name, "ERROR", str(e)))
    
    def test_api_connection(self):
        """Test conexión API"""
        response = requests.get(f"{self.base_url}/api/status", timeout=15)
        return response.status_code == 200
    
    def test_printers_endpoint(self):
        """Test endpoint de impresoras"""
        response = requests.get(f"{self.base_url}/api/printers", timeout=15)
        data = response.json()
        return response.status_code == 200 and "printers" in data
    
    def test_user_login(self):
        """Test login de usuario"""
        data = {"username": "admin", "password": "admin123"}
        response = requests.post(f"{self.base_url}/api/login", json=data, timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            self.session_id = result.get("session_id")
            return "session_id" in result
        return False
    
    def test_job_creation(self):
        """Test creación de trabajo"""
        data = {
            "filename": "test.zpl",
            "content": "^XA^FO50,50^A0N,50,50^FDTest^FS^XZ",
            "printer": "Test Printer",
            "copies": 1
        }
        response = requests.post(f"{self.base_url}/api/process-file", json=data, timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            return "job_id" in result
        return False
    
    def test_job_status(self):
        """Test estado de trabajo"""
        # Crear trabajo primero
        data = {
            "filename": "test_status.zpl",
            "content": "^XA^FO50,50^A0N,50,50^FDTest Status^FS^XZ",
            "printer": "Test Printer",
            "copies": 1
        }
        response = requests.post(f"{self.base_url}/api/process-file", json=data, timeout=5)
        
        if response.status_code == 200:
            job_id = response.json()["job_id"]
            time.sleep(2)  # Esperar procesamiento
            
            status_response = requests.get(f"{self.base_url}/api/jobs/{job_id}", timeout=5)
            return status_response.status_code == 200
        return False
    
    def test_statistics(self):
        """Test estadísticas"""
        response = requests.get(f"{self.base_url}/api/statistics", timeout=5)
        data = response.json()
        return response.status_code == 200 and "total_jobs" in data
    
    def test_backup_creation(self):
        """Test creación de backup"""
        response = requests.post(f"{self.base_url}/api/backup/create", timeout=10)
        return response.status_code == 200
    
    def test_backup_list(self):
        """Test lista de backups"""
        response = requests.get(f"{self.base_url}/api/backups", timeout=5)
        data = response.json()
        return response.status_code == 200 and isinstance(data, list)
    
    def test_notification_config(self):
        """Test configuración de notificaciones"""
        # Test GET
        response = requests.get(f"{self.base_url}/api/config/notifications", timeout=5)
        if response.status_code != 200:
            return False
        
        # Test POST
        config = {
            "desktop_enabled": True,
            "notify_on_error": True,
            "notify_on_success": False
        }
        response = requests.post(f"{self.base_url}/api/config/notifications", json=config, timeout=5)
        return response.status_code == 200
    
    def test_web_pages(self):
        """Test páginas web"""
        pages = ["/web/index.html", "/web/config.html", "/web/login.html"]
        
        for page in pages:
            response = requests.get(f"{self.base_url}{page}", timeout=5)
            if response.status_code != 200:
                return False
        return True
    
    def test_database_operations(self):
        """Test operaciones de base de datos"""
        from database import db
        
        # Test agregar trabajo
        job_id = db.add_job("test_db.zpl", "Test Printer", "zpl", 1, 100)
        if not job_id:
            return False
        
        # Test obtener trabajo
        job = db.get_job(job_id)
        if not job or job["filename"] != "test_db.zpl":
            return False
        
        # Test estadísticas
        stats = db.get_statistics()
        return "total_jobs" in stats
    
    def run_all_tests(self):
        """Ejecutar todos los tests"""
        print("🚀 Iniciando tests del sistema EtiquetadorZPL")
        print("=" * 50)
        
        # Tests de API
        self.test("Conexión API", self.test_api_connection)
        self.test("Endpoint impresoras", self.test_printers_endpoint)
        self.test("Login usuario", self.test_user_login)
        self.test("Creación trabajo", self.test_job_creation)
        self.test("Estado trabajo", self.test_job_status)
        self.test("Estadísticas", self.test_statistics)
        
        # Tests de configuración
        self.test("Config notificaciones", self.test_notification_config)
        
        # Tests de backup
        self.test("Creación backup", self.test_backup_creation)
        self.test("Lista backups", self.test_backup_list)
        
        # Tests web
        self.test("Páginas web", self.test_web_pages)
        
        # Tests de base de datos
        self.test("Operaciones BD", self.test_database_operations)
        
        # Resumen
        print("\n" + "=" * 50)
        print("📊 RESUMEN DE TESTS")
        print("=" * 50)
        
        passed = sum(1 for _, status, _ in self.results if status == "PASS")
        failed = sum(1 for _, status, _ in self.results if status in ["FAIL", "ERROR"])
        total = len(self.results)
        
        print(f"✅ Pasaron: {passed}/{total}")
        print(f"❌ Fallaron: {failed}/{total}")
        print(f"📈 Éxito: {(passed/total)*100:.1f}%")
        
        # Mostrar fallos
        failures = [(name, error) for name, status, error in self.results if status in ["FAIL", "ERROR"]]
        if failures:
            print("\n❌ TESTS FALLIDOS:")
            for name, error in failures:
                print(f"  - {name}: {error}")
        
        return passed == total

def main():
    """Función principal"""
    print("Detectando puerto de API...")
    
    # Detectar puerto
    ports = [8002, 8003, 8001, 8080, 8081]
    api_url = None
    
    for port in ports:
        try:
            print(f"Probando puerto {port}...")
            response = requests.get(f"http://localhost:{port}/api/status", timeout=10)
            if response.status_code == 200:
                api_url = f"http://localhost:{port}"
                print(f"✅ API encontrada en puerto {port}")
                break
        except Exception as e:
            print(f"Puerto {port}: {e}")
            continue
    
    if not api_url:
        print("❌ No se encontró la API ejecutándose")
        print("Inicia la API con: python final_api.py")
        return
    
    # Ejecutar tests
    tester = SystemTester(api_url)
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 TODOS LOS TESTS PASARON - Sistema funcionando correctamente")
    else:
        print("\n⚠️ ALGUNOS TESTS FALLARON - Revisar configuración")

if __name__ == "__main__":
    main()