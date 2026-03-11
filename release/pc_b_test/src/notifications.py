"""
Sistema de notificaciones para EtiquetadorZPL
"""

import json
from pathlib import Path

class NotificationManager:
    def __init__(self):
        self.config_file = Path('notification_config.json')
        self.config = self.load_config()
    
    def load_config(self):
        """Cargar configuración de notificaciones"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        
        return {
            "desktop_enabled": True,
            "email_enabled": False,
            "notify_on_error": True,
            "notify_on_success": False,
            "email_config": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "to_emails": []
            }
        }
    
    def save_config(self, config):
        """Guardar configuración"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self.config = config
            print(f"Configuración de notificaciones guardada: {config}")
            return True
        except Exception as e:
            print(f"Error guardando configuración de notificaciones: {e}")
            return False
    
    def _send_notification(self, title, message, level="info"):
        """Enviar notificación"""
        try:
            if self.config.get('desktop_enabled'):
                self._send_desktop_notification(title, message)
            print(f"NOTIFICATION: {title} - {message}")
        except Exception as e:
            print(f"Error enviando notificación: {e}")
    
    def _send_desktop_notification(self, title, message):
        """Notificación de escritorio Windows"""
        try:
            import subprocess
            # Usar PowerShell para mostrar notificación
            ps_script = f'''
            Add-Type -AssemblyName System.Windows.Forms
            $notify = New-Object System.Windows.Forms.NotifyIcon
            $notify.Icon = [System.Drawing.SystemIcons]::Information
            $notify.Visible = $true
            $notify.ShowBalloonTip(5000, "{title}", "{message}", [System.Windows.Forms.ToolTipIcon]::Info)
            Start-Sleep -Seconds 6
            $notify.Dispose()
            '''
            
            subprocess.run(["powershell", "-Command", ps_script], 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            print(f"Error notificación escritorio: {e}")
    
    def notify_job_completed(self, job_id, status, filename, printer, error_msg=None):
        """Notificar trabajo completado"""
        if status == 'failed' and self.config.get('notify_on_error'):
            self._send_notification(
                title="Error de Impresión",
                message=f"Archivo: {filename}\nImpresora: {printer}\nError: {error_msg}",
                level="error"
            )
        elif status == 'completed' and self.config.get('notify_on_success'):
            self._send_notification(
                title="Impresión Exitosa",
                message=f"Archivo: {filename}\nImpresora: {printer}",
                level="success"
            )

# Instancia global
notification_manager = NotificationManager()