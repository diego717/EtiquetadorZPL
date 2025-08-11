"""
Sistema de usuarios básico
"""

import json
import hashlib
import time
from pathlib import Path

class UserManager:
    def __init__(self):
        self.users_file = Path('users.json')
        self.sessions = {}
        self.load_users()
    
    def load_users(self):
        """Cargar usuarios"""
        try:
            if self.users_file.exists():
                with open(self.users_file, 'r') as f:
                    self.users = json.load(f)
            else:
                # Usuario admin por defecto
                self.users = {
                    "admin": {
                        "password_hash": self.hash_password("admin123"),
                        "role": "admin",
                        "created_at": time.time()
                    }
                }
                self.save_users()
        except:
            self.users = {}
    
    def save_users(self):
        """Guardar usuarios"""
        try:
            with open(self.users_file, 'w') as f:
                json.dump(self.users, f, indent=2)
        except Exception as e:
            print(f"Error guardando usuarios: {e}")
    
    def hash_password(self, password):
        """Hash de contraseña"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def authenticate(self, username, password):
        """Autenticar usuario"""
        if username in self.users:
            password_hash = self.hash_password(password)
            if self.users[username]["password_hash"] == password_hash:
                # Crear sesión
                session_id = hashlib.md5(f"{username}{time.time()}".encode()).hexdigest()
                self.sessions[session_id] = {
                    "username": username,
                    "role": self.users[username]["role"],
                    "created_at": time.time()
                }
                return session_id
        return None
    
    def validate_session(self, session_id):
        """Validar sesión"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            # Sesión válida por 24 horas
            if time.time() - session["created_at"] < 86400:
                return session
        return None
    
    def add_user(self, username, password, role="user"):
        """Agregar usuario"""
        if username not in self.users:
            self.users[username] = {
                "password_hash": self.hash_password(password),
                "role": role,
                "created_at": time.time()
            }
            self.save_users()
            return True
        return False
    
    def get_users(self):
        """Obtener lista de usuarios"""
        return [
            {
                "username": username,
                "role": data["role"],
                "created_at": data["created_at"]
            }
            for username, data in self.users.items()
        ]

# Instancia global
user_manager = UserManager()