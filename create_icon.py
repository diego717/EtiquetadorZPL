"""
Crear icono para EtiquetadorZPL
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_app_icon():
    """Crear icono de la aplicación"""
    
    # Crear imagen de 256x256 para alta calidad
    size = 256
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Colores
    bg_color = '#2c3e50'  # Azul oscuro
    accent_color = '#3498db'  # Azul claro
    text_color = '#ffffff'  # Blanco
    label_color = '#e74c3c'  # Rojo
    
    # Fondo circular
    margin = 10
    draw.ellipse([margin, margin, size-margin, size-margin], 
                fill=bg_color, outline=accent_color, width=4)
    
    # Dibujar impresora (rectángulo principal)
    printer_width = 120
    printer_height = 80
    printer_x = (size - printer_width) // 2
    printer_y = (size - printer_height) // 2 - 10
    
    # Cuerpo de la impresora
    draw.rectangle([printer_x, printer_y, 
                   printer_x + printer_width, printer_y + printer_height],
                  fill=accent_color, outline=text_color, width=2)
    
    # Pantalla de la impresora
    screen_width = 40
    screen_height = 20
    screen_x = printer_x + 10
    screen_y = printer_y + 15
    draw.rectangle([screen_x, screen_y,
                   screen_x + screen_width, screen_y + screen_height],
                  fill=bg_color, outline=text_color, width=1)
    
    # Botones de la impresora
    for i in range(3):
        btn_x = screen_x + screen_width + 15 + (i * 15)
        btn_y = screen_y + 5
        draw.ellipse([btn_x, btn_y, btn_x + 10, btn_y + 10],
                    fill=text_color)
    
    # Etiqueta saliendo de la impresora
    label_width = 60
    label_height = 30
    label_x = printer_x + printer_width - 20
    label_y = printer_y + printer_height - 15
    
    # Etiqueta principal
    draw.rectangle([label_x, label_y,
                   label_x + label_width, label_y + label_height],
                  fill=label_color, outline=text_color, width=2)
    
    # Líneas en la etiqueta (simulando texto/código de barras)
    for i in range(3):
        line_y = label_y + 8 + (i * 6)
        draw.rectangle([label_x + 5, line_y,
                       label_x + label_width - 5, line_y + 2],
                      fill=text_color)
    
    # Texto "ZPL" en la parte inferior
    try:
        # Intentar usar fuente del sistema
        font_size = 24
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
            except:
                font = ImageFont.load_default()
        
        text = "ZPL"
        # Obtener tamaño del texto
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        text_x = (size - text_width) // 2
        text_y = printer_y + printer_height + 20
        
        # Sombra del texto
        draw.text((text_x + 2, text_y + 2), text, fill='#34495e', font=font)
        # Texto principal
        draw.text((text_x, text_y), text, fill=text_color, font=font)
        
    except Exception as e:
        print(f"Error con fuente: {e}")
    
    # Guardar en diferentes tamaños
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    
    for s in sizes:
        resized = img.resize((s, s), Image.Resampling.LANCZOS)
        images.append(resized)
    
    # Guardar como ICO
    img.save('etiquetador_icon.ico', format='ICO', sizes=[(s, s) for s in sizes])
    
    # Guardar también como PNG para referencia
    img.save('etiquetador_icon.png', format='PNG')
    
    print("OK: Icono creado: etiquetador_icon.ico")
    print("OK: Preview creado: etiquetador_icon.png")
    
    return 'etiquetador_icon.ico'

if __name__ == "__main__":
    try:
        icon_path = create_app_icon()
        print(f"Icono listo: {icon_path}")
    except Exception as e:
        print(f"Error creando icono: {e}")
    
    input("Presiona Enter para continuar...")