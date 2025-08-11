"""
GUI simple para EtiquetadorZPL
"""

import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import requests

class SimpleGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EtiquetadorZPL")
        self.root.geometry("400x300")
        
        self.create_widgets()
    
    def create_widgets(self):
        """Crear widgets"""
        # Título
        title = tk.Label(self.root, text="🏷️ EtiquetadorZPL", font=("Arial", 16, "bold"))
        title.pack(pady=10)
        
        # Estado
        self.status_label = tk.Label(self.root, text="Verificando estado...", fg="orange")
        self.status_label.pack(pady=5)
        
        # Botones principales
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="🌐 Abrir Dashboard", command=self.open_dashboard, 
                 width=20, height=2).pack(pady=5)
        
        tk.Button(btn_frame, text="📊 Ver Estadísticas", command=self.show_stats, 
                 width=20, height=2).pack(pady=5)
        
        tk.Button(btn_frame, text="🔄 Verificar Estado", command=self.check_status, 
                 width=20, height=2).pack(pady=5)
        
        # Info
        info_frame = tk.Frame(self.root)
        info_frame.pack(pady=20, fill="x", padx=20)
        
        tk.Label(info_frame, text="Dashboard Web:", font=("Arial", 10, "bold")).pack()
        self.url_label = tk.Label(info_frame, text="http://localhost:8002/web/", 
                                 fg="blue", cursor="hand2")
        self.url_label.pack()
        self.url_label.bind("<Button-1>", lambda e: self.open_dashboard())
        
        # Verificar estado inicial
        self.root.after(1000, self.check_status)
    
    def check_status(self):
        """Verificar estado de la API"""
        try:
            response = requests.get("http://localhost:8002/api/status", timeout=3)
            if response.status_code == 200:
                self.status_label.config(text="✅ Sistema funcionando", fg="green")
                return True
        except:
            pass
        
        # Probar otros puertos
        for port in [8003, 8001, 8080]:
            try:
                response = requests.get(f"http://localhost:{port}/api/status", timeout=2)
                if response.status_code == 200:
                    self.status_label.config(text=f"✅ Sistema funcionando (puerto {port})", fg="green")
                    self.url_label.config(text=f"http://localhost:{port}/web/")
                    return True
            except:
                continue
        
        self.status_label.config(text="❌ Sistema no disponible", fg="red")
        return False
    
    def open_dashboard(self):
        """Abrir dashboard web"""
        url = self.url_label.cget("text")
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el navegador: {e}")
    
    def show_stats(self):
        """Mostrar estadísticas básicas"""
        try:
            url = self.url_label.cget("text").replace("/web/", "/api/statistics")
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                stats = response.json()
                
                msg = f"""📊 Estadísticas del Sistema

Total trabajos: {stats.get('total_jobs', 0)}
Completados: {stats.get('completed', 0)}
Fallidos: {stats.get('failed', 0)}
En proceso: {stats.get('processing', 0)}

Tiempo promedio: {stats.get('avg_processing_time', 0):.2f}s
"""
                messagebox.showinfo("Estadísticas", msg)
            else:
                messagebox.showerror("Error", "No se pudieron obtener estadísticas")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error obteniendo estadísticas: {e}")
    
    def run(self):
        """Ejecutar GUI"""
        self.root.mainloop()

if __name__ == "__main__":
    app = SimpleGUI()
    app.run()