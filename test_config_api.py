"""
Test de endpoints de configuración
"""

import requests
import json

def test_config_endpoints():
    """Probar endpoints de configuración"""
    
    base_url = "http://localhost:8002"
    
    print("=== Test de Endpoints de Configuración ===")
    
    # Test 1: GET notifications config
    try:
        response = requests.get(f"{base_url}/api/config/notifications")
        print(f"GET notifications: {response.status_code}")
        if response.status_code == 200:
            print(f"Config: {response.json()}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error GET notifications: {e}")
    
    # Test 2: POST notifications config
    try:
        test_config = {
            "desktop_enabled": True,
            "notify_on_error": True,
            "notify_on_success": False,
            "email_enabled": False,
            "email_config": {}
        }
        
        response = requests.post(
            f"{base_url}/api/config/notifications",
            json=test_config
        )
        print(f"POST notifications: {response.status_code}")
        if response.status_code == 200:
            print(f"Result: {response.json()}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error POST notifications: {e}")
    
    # Test 3: GET backup config
    try:
        response = requests.get(f"{base_url}/api/config/backup")
        print(f"GET backup: {response.status_code}")
        if response.status_code == 200:
            print(f"Config: {response.json()}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error GET backup: {e}")
    
    # Test 4: POST backup config
    try:
        test_config = {
            "enabled": True,
            "daily_backup": True,
            "weekly_backup": True,
            "keep_daily": 7,
            "keep_weekly": 4
        }
        
        response = requests.post(
            f"{base_url}/api/config/backup",
            json=test_config
        )
        print(f"POST backup: {response.status_code}")
        if response.status_code == 200:
            print(f"Result: {response.json()}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error POST backup: {e}")

if __name__ == "__main__":
    test_config_endpoints()
    input("Presiona Enter para continuar...")