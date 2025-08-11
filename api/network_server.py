"""
Servidor de red para acceso remoto
"""

import socket
import json
from final_api import FinalAPIHandler
import socketserver
import threading

class NetworkAPIHandler(FinalAPIHandler):
    def log_message(self, format, *args):
        # Log con IP del cliente
        client_ip = self.client_address[0]
        print(f"[{client_ip}] {format % args}")

class NetworkServer:
    def __init__(self, host="0.0.0.0", port=None):
        self.host = host
        self.port = port or self.find_free_port()
        self.server = None
    
    def find_free_port(self):
        """Encontrar puerto libre"""
        for port in range(8080, 8090):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', port))
                    return port
            except:
                continue
        return 8080
        
    def start(self):
        """Iniciar servidor de red"""
        try:
            self.server = socketserver.TCPServer((self.host, self.port), NetworkAPIHandler)
            self.server.allow_reuse_address = True
            
            # Obtener IP local
            local_ip = self.get_local_ip()
            
            print(f"Servidor de red iniciado:")
            print(f"  Local: http://localhost:{self.port}")
            print(f"  Red:   http://{local_ip}:{self.port}")
            print(f"  Dashboard: http://{local_ip}:{self.port}/web/")
            
            # Guardar configuración de red
            with open('network_config.json', 'w') as f:
                json.dump({
                    "host": self.host,
                    "port": self.port,
                    "local_ip": local_ip,
                    "enabled": True
                }, f, indent=2)
            
            self.server.serve_forever()
            
        except Exception as e:
            print(f"Error iniciando servidor de red: {e}")
    
    def get_local_ip(self):
        """Obtener IP local"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def stop(self):
        """Detener servidor"""
        if self.server:
            self.server.shutdown()

def start_network_server():
    """Iniciar servidor de red"""
    server = NetworkServer()
    server.start()

if __name__ == "__main__":
    start_network_server()