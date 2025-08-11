"""
Sistema de backup automático
"""

import shutil
import json
from datetime import datetime
from pathlib import Path

class BackupManager:
    def __init__(self, backup_dir="backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        self.config = self.load_config()
    
    def load_config(self):
        """Cargar configuración de backup"""
        try:
            with open('backup_config.json', 'r') as f:
                return json.load(f)
        except:
            return {
                "enabled": True,
                "daily_backup": True,
                "weekly_backup": True,
                "keep_daily": 7,
                "keep_weekly": 4
            }
    
    def save_config(self, config):
        """Guardar configuración"""
        with open('backup_config.json', 'w') as f:
            json.dump(config, f, indent=2)
        self.config = config
    
    def create_manual_backup(self, name=None):
        """Crear backup manual"""
        if not name:
            name = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_path = self.backup_dir / name
        return self._create_backup(backup_path, "manual")
    
    def _create_backup(self, backup_path, backup_type):
        """Crear backup en la ruta especificada"""
        try:
            backup_path.mkdir(exist_ok=True)
            files_backed_up = []
            
            # Backup de base de datos
            db_file = Path('etiquetador.db')
            if db_file.exists():
                shutil.copy2(db_file, backup_path / 'etiquetador.db')
                files_backed_up.append(f'etiquetador.db ({db_file.stat().st_size} bytes)')
                print(f"Backup: Base de datos copiada")
            
            # Backup de configuraciones
            config_files = ['config.ini', 'notification_config.json', 'backup_config.json']
            for config_file in config_files:
                config_path = Path(config_file)
                if config_path.exists():
                    shutil.copy2(config_path, backup_path / config_file)
                    files_backed_up.append(f'{config_file} ({config_path.stat().st_size} bytes)')
                    print(f"Backup: {config_file} copiado")
            
            # Backup de logs
            logs_dir = Path('logs')
            if logs_dir.exists() and logs_dir.is_dir():
                shutil.copytree(logs_dir, backup_path / 'logs', dirs_exist_ok=True)
                log_count = len(list(logs_dir.rglob('*')))
                files_backed_up.append(f'logs/ ({log_count} archivos)')
                print(f"Backup: Logs copiados")
            
            # Crear manifiesto detallado
            manifest = {
                "backup_type": backup_type,
                "created_at": datetime.now().isoformat(),
                "version": "1.0",
                "description": "Backup de EtiquetadorZPL",
                "files_backed_up": files_backed_up,
                "total_files": len(files_backed_up),
                "contents": {
                    "database": "Historial de trabajos de impresión y estadísticas",
                    "configurations": "Configuraciones de carpetas, impresoras y notificaciones",
                    "logs": "Archivos de log del sistema"
                }
            }
            
            with open(backup_path / 'manifest.json', 'w') as f:
                json.dump(manifest, f, indent=2, default=str)
            
            print(f"Backup completado: {len(files_backed_up)} elementos")
            return True
        except Exception as e:
            print(f"Error creando backup: {e}")
            return False
    
    def restore_backup(self, backup_name):
        """Restaurar desde backup"""
        backup_path = self.backup_dir / backup_name
        
        if not backup_path.exists():
            return False, "Backup no encontrado"
        
        try:
            # Restaurar base de datos
            if (backup_path / 'etiquetador.db').exists():
                shutil.copy2(backup_path / 'etiquetador.db', 'etiquetador.db')
            
            # Restaurar configuraciones
            config_files = ['config.ini', 'notification_config.json', 'backup_config.json']
            for config_file in config_files:
                backup_file = backup_path / config_file
                if backup_file.exists():
                    shutil.copy2(backup_file, config_file)
            
            return True, "Backup restaurado exitosamente"
        except Exception as e:
            return False, f"Error restaurando backup: {e}"
    
    def list_backups(self):
        """Listar backups disponibles"""
        backups = []
        
        for backup_dir in self.backup_dir.iterdir():
            if backup_dir.is_dir():
                manifest_file = backup_dir / 'manifest.json'
                
                if manifest_file.exists():
                    try:
                        with open(manifest_file, 'r') as f:
                            manifest = json.load(f)
                        
                        backups.append({
                            "name": backup_dir.name,
                            "type": manifest.get("backup_type", "unknown"),
                            "created_at": manifest.get("created_at"),
                            "size": sum(f.stat().st_size for f in backup_dir.rglob('*') if f.is_file())
                        })
                    except:
                        pass
        
        return sorted(backups, key=lambda x: x.get('created_at', ''), reverse=True)

# Instancia global
backup_manager = BackupManager()