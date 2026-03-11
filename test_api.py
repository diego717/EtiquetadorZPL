"""
Script para probar la API
"""

import requests
import time
from pathlib import Path

def test_api():
    """Probar conexión a la API"""
    
    print("=== Test de API ===\n")
    
    # Leer puerto
    api_port = None
    try:
        with open('api_port.txt', 'r') as f:
            api_port = f.read().strip()
        print(f"Puerto encontrado: {api_port}")
    except:
        print("No se encontró api_port.txt")
        api_port = "8002"
        print(f"Usando puerto por defecto: {api_port}")
    
    base_url = f"http://localhost:{api_port}"
    
    # Test 1: Status
    try:
        print(f"\n1. Probando status: {base_url}/api/status")
        response = requests.get(f"{base_url}/api/status", timeout=5)
        if response.status_code == 200:
            print("✅ API responde correctamente")
            print(f"   Respuesta: {response.json()}")
        else:
            print(f"❌ API error: {response.status_code}")
    except Exception as e:
        print(f"❌ No se puede conectar a la API: {e}")
        return False
    
    # Test 2: Dashboard
    try:
        print(f"\n2. Probando dashboard: {base_url}/web/")
        response = requests.get(f"{base_url}/web/", timeout=5)
        if response.status_code == 200:
            print("✅ Dashboard accesible")
        else:
            print(f"❌ Dashboard error: {response.status_code}")
    except Exception as e:
        print(f"❌ Dashboard no accesible: {e}")
    
    # Test 3: Archivos web
    web_files = ['index.html', 'config.html', 'login.html']
    for file in web_files:
        try:
            print(f"\n3. Probando {file}: {base_url}/web/{file}")
            response = requests.get(f"{base_url}/web/{file}", timeout=5)
            if response.status_code == 200:
                print(f"✅ {file} accesible")
            else:
                print(f"❌ {file} error: {response.status_code}")
        except Exception as e:
            print(f"❌ {file} no accesible: {e}")
    
    print(f"\n=== Enlaces útiles ===")
    print(f"Dashboard: {base_url}/web/")
    print(f"API Docs: {base_url}/docs")
    print(f"Status: {base_url}/api/status")
    
    return True

if __name__ == "__main__":
    test_api()
    input("\nPresiona Enter para continuar...")