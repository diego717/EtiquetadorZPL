"""
Tests de rendimiento
"""

import time
import requests
import threading
from pathlib import Path

class PerformanceTester:
    def __init__(self, base_url="http://localhost:8002"):
        self.base_url = base_url
    
    def test_api_response_time(self):
        """Test tiempo de respuesta API"""
        print("🚀 Test tiempo respuesta API...")
        
        endpoints = [
            "/api/status",
            "/api/printers", 
            "/api/statistics",
            "/api/jobs"
        ]
        
        for endpoint in endpoints:
            start = time.time()
            response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
            duration = time.time() - start
            
            status = "✅" if duration < 1.0 else "⚠️" if duration < 3.0 else "❌"
            print(f"  {endpoint}: {duration:.3f}s {status}")
    
    def test_concurrent_jobs(self, num_jobs=10):
        """Test trabajos concurrentes"""
        print(f"🔄 Test {num_jobs} trabajos concurrentes...")
        
        def create_job(job_id):
            data = {
                "filename": f"concurrent_test_{job_id}.zpl",
                "content": f"^XA^FO50,50^A0N,50,50^FDTest {job_id}^FS^XZ",
                "printer": "Test Printer",
                "copies": 1
            }
            
            start = time.time()
            response = requests.post(f"{self.base_url}/api/process-file", json=data, timeout=10)
            duration = time.time() - start
            
            return response.status_code == 200, duration
        
        # Ejecutar trabajos concurrentes
        threads = []
        results = []
        
        start_time = time.time()
        
        for i in range(num_jobs):
            thread = threading.Thread(target=lambda i=i: results.append(create_job(i)))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        total_time = time.time() - start_time
        
        successful = sum(1 for success, _ in results if success)
        avg_time = sum(duration for _, duration in results) / len(results)
        
        print(f"  Exitosos: {successful}/{num_jobs}")
        print(f"  Tiempo total: {total_time:.2f}s")
        print(f"  Tiempo promedio: {avg_time:.3f}s")
        print(f"  Throughput: {num_jobs/total_time:.1f} jobs/s")
    
    def test_file_processing_speed(self):
        """Test velocidad procesamiento archivos"""
        print("📁 Test velocidad procesamiento...")
        
        # Crear archivo temporal
        test_content = "^XA^FO50,50^A0N,50,50^FDSpeed Test^FS^XZ"
        
        # Test diferentes tamaños
        sizes = [100, 1000, 5000]  # bytes
        
        for size in sizes:
            content = test_content * (size // len(test_content))
            
            data = {
                "filename": f"speed_test_{size}.zpl",
                "content": content,
                "printer": "Test Printer",
                "copies": 1
            }
            
            start = time.time()
            response = requests.post(f"{self.base_url}/api/process-file", json=data, timeout=10)
            duration = time.time() - start
            
            if response.status_code == 200:
                speed = len(content) / duration / 1024  # KB/s
                print(f"  {size} bytes: {duration:.3f}s ({speed:.1f} KB/s)")
    
    def test_database_performance(self):
        """Test rendimiento base de datos"""
        print("🗄️ Test rendimiento base de datos...")
        
        from database import db
        
        # Test inserción masiva
        start = time.time()
        job_ids = []
        
        for i in range(100):
            job_id = db.add_job(f"perf_test_{i}.zpl", "Test Printer", "zpl", 1, 100)
            job_ids.append(job_id)
        
        insert_time = time.time() - start
        
        # Test consulta masiva
        start = time.time()
        
        for job_id in job_ids[:10]:  # Solo primeros 10
            job = db.get_job(job_id)
        
        query_time = time.time() - start
        
        print(f"  100 inserciones: {insert_time:.3f}s ({100/insert_time:.1f} ops/s)")
        print(f"  10 consultas: {query_time:.3f}s ({10/query_time:.1f} ops/s)")
    
    def run_performance_tests(self):
        """Ejecutar todos los tests de rendimiento"""
        print("⚡ TESTS DE RENDIMIENTO")
        print("=" * 40)
        
        self.test_api_response_time()
        print()
        
        self.test_concurrent_jobs(5)
        print()
        
        self.test_file_processing_speed()
        print()
        
        self.test_database_performance()
        print()
        
        print("✅ Tests de rendimiento completados")

def main():
    """Función principal"""
    # Detectar puerto
    ports = [8002, 8003, 8001]
    api_url = None
    
    for port in ports:
        try:
            response = requests.get(f"http://localhost:{port}/api/status", timeout=2)
            if response.status_code == 200:
                api_url = f"http://localhost:{port}"
                break
        except:
            continue
    
    if not api_url:
        print("❌ API no encontrada")
        return
    
    tester = PerformanceTester(api_url)
    tester.run_performance_tests()

if __name__ == "__main__":
    main()