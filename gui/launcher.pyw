import subprocess
import sys
import time

def start_api():
    """Iniciar API en background"""
    try:
        api_process = subprocess.Popen(
            [sys.executable, "final_api.py"],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        time.sleep(2)  # Esperar que inicie
        return api_process
    except:
        return None

# Iniciar API
api_process = start_api()

try: 
    from main_gui_optimized import EtiquetadorGUIOptimized 
    app = EtiquetadorGUIOptimized() 
    app.run() 
except ImportError: 
    try:
        from main_gui import EtiquetadorGUI 
        app = EtiquetadorGUI() 
        app.run() 
    except Exception as e: 
        import tkinter as tk 
        from tkinter import messagebox 
        root = tk.Tk() 
        root.withdraw() 
        messagebox.showerror("Error", f"Error: {e}") 
        root.destroy() 
except Exception as e: 
    import tkinter as tk 
    from tkinter import messagebox 
    root = tk.Tk() 
    root.withdraw() 
    messagebox.showerror("Error", f"Error: {e}") 
    root.destroy() 
finally:
    # Cerrar API al salir
    if 'api_process' in locals() and api_process:
        try:
            api_process.terminate()
        except:
            pass