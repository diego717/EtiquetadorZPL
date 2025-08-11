"""
Test validación de impresoras
"""

import requests
import time

def test_printer_validation():
    """Probar validación de impresoras"""
    
    # Detectar puerto API
    try:
        with open('api_port.txt', 'r') as f:
            port = f.read().strip()
    except:
        port = "8002"
    
    api_url = f"http://localhost:{port}"
    
    print("=== Test Validacion Impresoras ===")
    print(f"API: {api_url}")
    
    # Test 1: Impresora válida
    print("\n1. Test impresora valida...")
    try:
        # Obtener impresoras disponibles
        response = requests.get(f"{api_url}/api/printers")
        printers = response.json()["printers"]
        
        if printers:
            valid_printer = printers[0]
            print(f"Usando impresora: {valid_printer}")
            
            data = {
                "filename": "test_valid.zpl",
                "content": "^XA^FO50,50^A0N,50,50^FDTest Valid^FS^XZ",
                "printer": valid_printer,
                "copies": 1
            }
            
            response = requests.post(f"{api_url}/api/process-file", json=data)
            if response.status_code == 200:
                job_id = response.json()["job_id"]
                print(f"Trabajo creado: {job_id}")
                
                # Esperar procesamiento
                time.sleep(3)
                
                # Verificar estado
                response = requests.get(f"{api_url}/api/jobs/{job_id}")
                job = response.json()
                print(f"Estado: {job['status']}")
                if job.get('error_message'):
                    print(f"Error: {job['error_message']}")
        else:
            print("No hay impresoras disponibles")
    
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 2: Impresora inválida
    print("\n2. Test impresora invalida...")
    try:
        data = {
            "filename": "test_invalid.zpl",
            "content": "^XA^FO50,50^A0N,50,50^FDTest Invalid^FS^XZ",
            "printer": "IMPRESORA_INEXISTENTE",
            "copies": 1
        }
        
        response = requests.post(f"{api_url}/api/process-file", json=data)
        if response.status_code == 200:
            job_id = response.json()["job_id"]
            print(f"Trabajo creado: {job_id}")
            
            # Esperar procesamiento
            time.sleep(3)
            
            # Verificar estado
            response = requests.get(f"{api_url}/api/jobs/{job_id}")
            job = response.json()
            print(f"Estado: {job['status']}")
            if job.get('error_message'):
                print(f"Error: {job['error_message']}")
                print("CORRECTO: Impresora invalida detectada")
            else:
                print("ERROR: Deberia haber fallado")
    
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n=== Test Completado ===")

if __name__ == "__main__":
    test_printer_validation()