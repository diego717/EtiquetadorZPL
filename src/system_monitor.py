"""
Monitor del sistema EtiquetadorZPL
"""

import psutil
import time
import json
from datetime import datetime
from pathlib import Path

class SystemMonitor:
    def __init__(self):
        self.metrics = []
        self.alerts = []
    
    def collect_metrics(self):
        """Recopilar métricas del sistema"""
        try:
            # Métricas básicas
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('.')
            
            # Procesos Python (EtiquetadorZPL)
            python_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
                if 'python' in proc.info['name'].lower():
                    python_processes.append({
                        'pid': proc.info['pid'],
                        'cpu': proc.info['cpu_percent'],
                        'memory_mb': proc.info['memory_info'].rss / 1024 / 1024
                    })
            
            # Base de datos
            db_size = 0
            if Path('etiquetador.db').exists():
                db_size = Path('etiquetador.db').stat().st_size / 1024 / 1024  # MB
            
            # Logs
            log_size = 0
            if Path('logs').exists():
                for log_file in Path('logs').rglob('*.log'):
                    log_size += log_file.stat().st_size
                log_size = log_size / 1024 / 1024  # MB
            
            metrics = {
                'timestamp': datetime.now().isoformat(),
                'system': {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_available_gb': memory.available / 1024 / 1024 / 1024,
                    'disk_percent': disk.percent,
                    'disk_free_gb': disk.free / 1024 / 1024 / 1024
                },
                'etiquetador': {
                    'python_processes': len(python_processes),
                    'total_cpu': sum(p['cpu'] for p in python_processes),
                    'total_memory_mb': sum(p['memory_mb'] for p in python_processes),
                    'db_size_mb': db_size,
                    'log_size_mb': log_size
                },
                'processes': python_processes
            }
            
            self.metrics.append(metrics)
            
            # Mantener solo últimas 100 métricas
            if len(self.metrics) > 100:
                self.metrics = self.metrics[-100:]
            
            # Verificar alertas
            self.check_alerts(metrics)
            
            return metrics
            
        except Exception as e:
            print(f"Error recopilando métricas: {e}")
            return None
    
    def check_alerts(self, metrics):
        """Verificar condiciones de alerta"""
        alerts = []
        
        # CPU alto
        if metrics['system']['cpu_percent'] > 80:
            alerts.append({
                'type': 'high_cpu',
                'message': f"CPU alto: {metrics['system']['cpu_percent']:.1f}%",
                'severity': 'warning'
            })
        
        # Memoria alta
        if metrics['system']['memory_percent'] > 85:
            alerts.append({
                'type': 'high_memory',
                'message': f"Memoria alta: {metrics['system']['memory_percent']:.1f}%",
                'severity': 'warning'
            })
        
        # Disco lleno
        if metrics['system']['disk_percent'] > 90:
            alerts.append({
                'type': 'disk_full',
                'message': f"Disco lleno: {metrics['system']['disk_percent']:.1f}%",
                'severity': 'critical'
            })
        
        # Base de datos grande
        if metrics['etiquetador']['db_size_mb'] > 100:
            alerts.append({
                'type': 'large_database',
                'message': f"Base de datos grande: {metrics['etiquetador']['db_size_mb']:.1f}MB",
                'severity': 'info'
            })
        
        # Logs grandes
        if metrics['etiquetador']['log_size_mb'] > 50:
            alerts.append({
                'type': 'large_logs',
                'message': f"Logs grandes: {metrics['etiquetador']['log_size_mb']:.1f}MB",
                'severity': 'info'
            })
        
        # Agregar alertas con timestamp
        for alert in alerts:
            alert['timestamp'] = datetime.now().isoformat()
            self.alerts.append(alert)
        
        # Mantener solo últimas 50 alertas
        if len(self.alerts) > 50:
            self.alerts = self.alerts[-50:]
    
    def get_summary(self):
        """Obtener resumen del sistema"""
        if not self.metrics:
            return None
        
        latest = self.metrics[-1]
        
        return {
            'status': 'running',
            'uptime_minutes': len(self.metrics),  # Aproximado
            'current_metrics': latest,
            'recent_alerts': self.alerts[-5:] if self.alerts else [],
            'total_alerts': len(self.alerts)
        }
    
    def save_metrics(self):
        """Guardar métricas a archivo"""
        try:
            with open('system_metrics.json', 'w') as f:
                json.dump({
                    'metrics': self.metrics[-10:],  # Solo últimas 10
                    'alerts': self.alerts[-10:]     # Solo últimas 10
                }, f, indent=2)
        except Exception as e:
            print(f"Error guardando métricas: {e}")
    
    def start_monitoring(self, interval=60):
        """Iniciar monitoreo continuo"""
        print(f"Iniciando monitor del sistema (intervalo: {interval}s)")
        
        try:
            while True:
                metrics = self.collect_metrics()
                if metrics:
                    print(f"CPU: {metrics['system']['cpu_percent']:.1f}% | "
                          f"RAM: {metrics['system']['memory_percent']:.1f}% | "
                          f"Procesos Python: {metrics['etiquetador']['python_processes']}")
                
                self.save_metrics()
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("Monitor detenido")
        except Exception as e:
            print(f"Error en monitor: {e}")

# Instancia global
system_monitor = SystemMonitor()

def main():
    """Función principal"""
    print("=== Monitor Sistema EtiquetadorZPL ===")
    print("1. Mostrar métricas actuales")
    print("2. Iniciar monitoreo continuo")
    print("3. Mostrar alertas")
    print("4. Salir")
    
    choice = input("Selecciona opción (1-4): ")
    
    if choice == "1":
        metrics = system_monitor.collect_metrics()
        if metrics:
            print(json.dumps(metrics, indent=2))
    
    elif choice == "2":
        interval = input("Intervalo en segundos (60): ") or "60"
        system_monitor.start_monitoring(int(interval))
    
    elif choice == "3":
        if system_monitor.alerts:
            for alert in system_monitor.alerts[-10:]:
                print(f"{alert['timestamp']}: {alert['message']} ({alert['severity']})")
        else:
            print("No hay alertas")
    
    elif choice == "4":
        return
    
    else:
        print("Opción inválida")

if __name__ == "__main__":
    main()