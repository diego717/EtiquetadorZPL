import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import io

def mostrar_vista_previa(imagen_bytes, contenido_zpl, callback_imprimir):
    """Muestra vista previa de la etiqueta ZPL"""
    
    ventana = tk.Toplevel()
    ventana.title("Vista Previa - Etiqueta ZPL")
    ventana.geometry("650x500")
    ventana.resizable(False, False)
    
    # Cargar imagen
    try:
        imagen = Image.open(io.BytesIO(imagen_bytes))
        # Redimensionar para vista previa (100% más grande)
        imagen.thumbnail((600, 400), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(imagen)
        
        # Mostrar imagen
        label_img = tk.Label(ventana, image=photo)
        label_img.image = photo  # Mantener referencia
        label_img.pack(pady=10)
        
    except Exception as e:
        tk.Label(ventana, text=f"Error al cargar imagen: {e}").pack(pady=10)
    
    # Botones
    frame_botones = tk.Frame(ventana)
    frame_botones.pack(pady=10)
    
    def imprimir_y_cerrar():
        ventana.destroy()
        callback_imprimir()
    
    def cancelar():
        from tkinter import messagebox
        messagebox.showinfo("Cancelado", "❌ Impresión cancelada por el usuario")
        ventana.destroy()
    
    ttk.Button(frame_botones, text="✅ Imprimir", command=imprimir_y_cerrar).pack(side=tk.LEFT, padx=5)
    ttk.Button(frame_botones, text="❌ Cancelar", command=cancelar).pack(side=tk.LEFT, padx=5)
    
    # Centrar ventana
    ventana.transient()
    ventana.grab_set()
    ventana.focus_set()