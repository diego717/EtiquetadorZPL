"""Recortador de fotos para tarjetas de identificación.

Herramienta local para encuadrar rostros por lote, revisar cada resultado y
exportar imágenes preparadas para credenciales.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps, ImageStat, ImageTk, UnidentifiedImageError


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
ASPECT_PRESETS = {
    "3:4 (identificación)": 3 / 4,
    "4:5": 4 / 5,
    "1:1": 1.0,
    "2:3 (foto carné)": 2 / 3,
    "5:7 (retrato)": 5 / 7,
    "35 × 45 mm (documento)": 35 / 45,
    "9:16 (vertical)": 9 / 16,
    "4:3 (horizontal)": 4 / 3,
    "16:9": 16 / 9,
}
EXPORT_FORMATS = {
    "JPG": (".jpg", "JPEG"),
    "PNG": (".png", "PNG"),
    "WEBP": (".webp", "WEBP"),
    "TIFF": (".tiff", "TIFF"),
    "BMP": (".bmp", "BMP"),
}


def compute_face_crop(
    image_size: tuple[int, int],
    face_box: tuple[int, int, int, int],
    eye_line: Optional[float],
    hair_margin: float,
    ratio: float,
    eye_position: float,
) -> tuple[float, float, float, float]:
    """Encuadre vertical con espacio configurable por encima de la cara.

    Función pura para que las pruebas puedan verificar el encuadre sin abrir una ventana.
    `eye_line` llega ya en `None` cuando la alineación de ojos está desactivada.
    """
    x, y, width, height = (float(value) for value in face_box)
    image_w, image_h = image_size
    maximum_h = min(image_h, image_w / ratio)
    # La cara no incluye el cabello para la mayoría de detectores. Se reserva un
    # margen superior y se aleja levemente el cuadro para incluir cabeza y hombros.
    face_fill = max(0.34, min(0.46, 0.48 - hair_margin * 0.20))
    crop_h = min(maximum_h, max(height / face_fill, width / (ratio * 0.68)))
    crop_h = max(min(crop_h, maximum_h), min(maximum_h, 100.0))
    crop_w = crop_h * ratio
    center_x = x + width / 2
    if eye_line is not None:
        top = eye_line - crop_h * (eye_position / 100)
    else:
        margin = min(max(hair_margin, 0.08), 0.35)
        top = y + height / 2 - crop_h * (margin + height / (2 * crop_h))
    left = center_x - crop_w / 2
    left = min(max(0.0, left), image_w - crop_w)
    top = min(max(0.0, top), image_h - crop_h)
    return (left, top, left + crop_w, top + crop_h)


@dataclass
class PhotoItem:
    path: Path
    image: Image.Image
    crop: tuple[float, float, float, float]
    face_found: bool = False
    face_box: Optional[tuple[int, int, int, int]] = None
    eye_line: Optional[float] = None
    eyes_checked: bool = False
    hair_margin: float = 0.20
    brightness: float = 1.0
    contrast: float = 1.0


class ModernSlider(tk.Canvas):
    """Deslizador liviano, sin la apariencia estriada del control nativo."""

    def __init__(self, parent, *, from_: float, to: float, variable: tk.DoubleVar, command, accent: str = "#1677b8", **kwargs) -> None:
        super().__init__(parent, height=26, background="#f4f7fb", highlightthickness=0, bd=0, cursor="hand2", **kwargs)
        self.minimum = from_
        self.maximum = to
        self.variable = variable
        self.command = command
        self.accent = accent
        self.variable.trace_add("write", self._redraw_from_variable)
        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", self._move_thumb)
        self.bind("<B1-Motion>", self._move_thumb)

    def _ratio(self) -> float:
        value = min(self.maximum, max(self.minimum, float(self.variable.get())))
        return (value - self.minimum) / (self.maximum - self.minimum)

    def _redraw_from_variable(self, *_args) -> None:
        self._draw()

    def _draw(self, _event=None) -> None:
        self.delete("all")
        width, height = max(self.winfo_width(), 20), max(self.winfo_height(), 20)
        padding, center_y = 11, height // 2
        end_x = width - padding
        thumb_x = padding + (end_x - padding) * self._ratio()
        self.create_line(padding, center_y, end_x, center_y, fill="#d5e0ea", width=6, capstyle="round")
        self.create_line(padding, center_y, thumb_x, center_y, fill=self.accent, width=6, capstyle="round")
        self.create_oval(thumb_x - 8, center_y - 8, thumb_x + 8, center_y + 8, fill="white", outline=self.accent, width=2)

    def _move_thumb(self, event) -> None:
        width = max(self.winfo_width(), 20)
        ratio = min(1.0, max(0.0, (event.x - 11) / max(1, width - 22)))
        value = self.minimum + (self.maximum - self.minimum) * ratio
        self.variable.set(round(value, 1))
        self.command(str(value))


class FaceCropperApp:
    """Aplicación de escritorio para recortar retratos con revisión manual."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Recortador de fotos para credenciales")
        self.root.geometry("1200x760")
        self.root.minsize(950, 620)

        self.photos: list[PhotoItem] = []
        self.current_index: Optional[int] = None
        self._preview_photo: Optional[ImageTk.PhotoImage] = None
        self._display_origin = (0, 0)
        self._display_scale = 1.0
        self._drag_start: Optional[tuple[float, float, tuple[float, float, float, float]]] = None
        self._face_cascade: Optional[cv2.CascadeClassifier] = None
        self._eye_cascade: Optional[cv2.CascadeClassifier] = None

        self.aspect_var = tk.StringVar(value="3:4 (identificación)")
        self.custom_aspect_var = tk.StringVar(value="3:4")
        self.output_dir_var = tk.StringVar()
        self.format_var = tk.StringVar(value="JPG")
        self.suffix_var = tk.StringVar()
        self.brightness_var = tk.DoubleVar(value=0)
        self.contrast_var = tk.DoubleVar(value=0)
        self.hair_margin_var = tk.DoubleVar(value=20)
        self.align_eyes_var = tk.BooleanVar(value=True)
        self.eye_position_var = tk.DoubleVar(value=40)
        self.brightness_text = tk.StringVar(value="0")
        self.contrast_text = tk.StringVar(value="0")
        self.hair_margin_text = tk.StringVar(value="20%")
        self.eye_position_text = tk.StringVar(value="40%")
        self.width_var = tk.StringVar()
        self.height_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Agregá fotos para comenzar.")

        self._build_ui()

    def _build_ui(self) -> None:
        root = self.root
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background="#f4f7fb")
        style.configure("TLabel", background="#f4f7fb", foreground="#26364a", font=("Segoe UI", 9))
        style.configure("TLabelframe", background="#f4f7fb", bordercolor="#d6e0eb")
        style.configure("TLabelframe.Label", background="#f4f7fb", foreground="#145a8d", font=("Segoe UI Semibold", 10))
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 9), foreground="white", background="#1677b8", padding=(13, 7), borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#0f6098"), ("pressed", "#0b4a75")])
        style.configure("Secondary.TButton", font=("Segoe UI", 9), foreground="#1d557c", background="#e7f1f8", padding=(10, 6), borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#d4e8f5"), ("pressed", "#c5deef")])
        style.configure("Auto.TButton", font=("Segoe UI Semibold", 9), foreground="white", background="#6c4ba3", padding=(10, 6), borderwidth=0)
        style.map("Auto.TButton", background=[("active", "#583888"), ("pressed", "#462c6d")])
        style.configure("Success.TButton", font=("Segoe UI Semibold", 9), foreground="white", background="#11806a", padding=(13, 7), borderwidth=0)
        style.map("Success.TButton", background=[("active", "#0c6655"), ("pressed", "#084f43")])
        style.configure("Danger.TButton", font=("Segoe UI", 9), foreground="#a33131", background="#fdecec", padding=(10, 6), borderwidth=0)
        style.map("Danger.TButton", background=[("active", "#f9d8d8"), ("pressed", "#f1c5c5")])
        root.configure(background="#f4f7fb")
        root.columnconfigure(0, minsize=230)
        root.columnconfigure(1, weight=1, minsize=450)
        root.columnconfigure(2, minsize=325)
        root.rowconfigure(2, weight=1)

        header = tk.Frame(root, background="#0e5f94", padx=18, pady=12)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        tk.Label(header, text="Recortador de fotos", background="#0e5f94", foreground="white",
                 font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(header, text="Encuadrá retratos para credenciales y exportá todo el lote en minutos.",
                 background="#0e5f94", foreground="#dceefa", font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))
        tk.Label(header, text="TRABAJO LOCAL  ·  VISTA PREVIA  ·  EXPORTACIÓN POR LOTE", background="#0e5f94",
                 foreground="#b9d9ed", font=("Segoe UI Semibold", 8)).pack(anchor="e", side="right", pady=(0, 4))

        toolbar = ttk.Frame(root, style="App.TFrame", padding=(10, 10, 10, 5))
        toolbar.grid(row=1, column=0, columnspan=3, sticky="ew")
        ttk.Button(toolbar, text="+  Agregar fotos", command=self.add_photos, style="Primary.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="▣  Agregar carpeta", command=self.add_folder, style="Secondary.TButton").pack(side="left", padx=6)
        ttk.Button(toolbar, text="−  Quitar seleccionada", command=self.remove_current, style="Secondary.TButton").pack(side="left", padx=6)
        ttk.Button(toolbar, text="Vaciar lista", command=self.clear_photos, style="Danger.TButton").pack(side="left", padx=6)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(toolbar, text="Detectar y encuadrar todas", command=self.auto_crop_all, style="Auto.TButton").pack(side="left")

        list_frame = ttk.LabelFrame(root, text="Fotos", padding=8)
        list_frame.grid(row=2, column=0, sticky="nsew", padx=(10, 5), pady=(5, 5))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.photo_list = tk.Listbox(list_frame, exportselection=False, width=34, relief="flat", borderwidth=0,
                                     background="#ffffff", foreground="#26364a", selectbackground="#1677b8",
                                     selectforeground="white", font=("Segoe UI", 10), activestyle="none")
        self.photo_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.photo_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.photo_list.configure(yscrollcommand=scrollbar.set)
        self.photo_list.bind("<<ListboxSelect>>", self.on_photo_selected)

        sidebar = ttk.Frame(root, style="App.TFrame", padding=(5, 5, 10, 10))
        sidebar.grid(row=2, column=2, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)

        preview_frame = ttk.LabelFrame(root, text="Vista previa — arrastrá el marco para ajustarlo", padding=8)
        preview_frame.grid(row=2, column=1, sticky="nsew", padx=5, pady=(5, 10))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(preview_frame, background="#242424", highlightthickness=0, cursor="fleur")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self.refresh_preview())
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag_crop)
        self.canvas.bind("<ButtonRelease-1>", self.end_drag)

        preview_status = ttk.Frame(preview_frame, padding=(0, 7, 0, 0))
        preview_status.grid(row=1, column=0, sticky="ew")
        self.preview_info = ttk.Label(preview_status, text="")
        self.preview_info.pack(side="left")

        self._build_sidebar(sidebar)
        footer = ttk.Frame(root, padding=(10, 2, 10, 8))
        footer.grid(row=3, column=0, columnspan=3, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        return

        controls = ttk.Frame(preview_frame, padding=(0, 8, 0, 0))
        controls.grid(row=1, column=0, sticky="ew")
        ttk.Button(controls, text="− Alejar", command=lambda: self.zoom_current(1.12), style="Secondary.TButton").pack(side="left", padx=(0, 5))
        ttk.Button(controls, text="+ Acercar", command=lambda: self.zoom_current(0.89), style="Secondary.TButton").pack(side="left", padx=5)
        ttk.Button(controls, text="Centrar", command=self.center_current, style="Secondary.TButton").pack(side="left", padx=5)
        ttk.Button(controls, text="Detectar esta foto", command=self.auto_crop_current, style="Auto.TButton").pack(side="left", padx=5)
        self.preview_info = ttk.Label(controls, text="")
        self.preview_info.pack(side="right")

        adjustments = ttk.LabelFrame(preview_frame, text="Ajustes de esta foto", padding=(8, 5))
        adjustments.grid(row=2, column=0, sticky="ew")
        adjustments.columnconfigure(1, weight=1)
        adjustments.columnconfigure(4, weight=1)
        adjustments.columnconfigure(7, weight=1)
        ttk.Label(adjustments, text="Brillo").grid(row=0, column=0, sticky="w")
        ttk.Scale(adjustments, from_=-60, to=60, variable=self.brightness_var,
                  command=self.change_brightness).grid(row=0, column=1, sticky="ew", padx=(6, 4))
        ttk.Label(adjustments, textvariable=self.brightness_text, width=5).grid(row=0, column=2, sticky="w")
        ttk.Label(adjustments, text="Contraste").grid(row=0, column=3, sticky="w", padx=(12, 0))
        ttk.Scale(adjustments, from_=-60, to=60, variable=self.contrast_var,
                  command=self.change_contrast).grid(row=0, column=4, sticky="ew", padx=(6, 4))
        ttk.Label(adjustments, textvariable=self.contrast_text, width=5).grid(row=0, column=5, sticky="w")
        ttk.Button(adjustments, text="Auto luz", command=self.auto_adjust_current, style="Auto.TButton").grid(row=0, column=6, padx=(12, 0))
        ttk.Button(adjustments, text="Restablecer", command=self.reset_adjustments, style="Secondary.TButton").grid(row=0, column=7, padx=(6, 0), sticky="e")

        hair_controls = ttk.Frame(adjustments)
        hair_controls.grid(row=1, column=0, columnspan=8, sticky="ew", pady=(7, 0))
        hair_controls.columnconfigure(1, weight=1)
        ttk.Label(hair_controls, text="Margen superior para cabello").grid(row=0, column=0, sticky="w")
        ttk.Scale(hair_controls, from_=8, to=35, variable=self.hair_margin_var,
                  command=self.change_hair_margin).grid(row=0, column=1, sticky="ew", padx=(10, 5))
        ttk.Label(hair_controls, textvariable=self.hair_margin_text, width=5).grid(row=0, column=2, sticky="w")
        ttk.Label(hair_controls, text="Reencuadra con más espacio por encima de la cabeza.").grid(row=0, column=3, sticky="w", padx=(10, 0))

        eye_controls = ttk.Frame(adjustments)
        eye_controls.grid(row=2, column=0, columnspan=8, sticky="ew", pady=(6, 0))
        eye_controls.columnconfigure(2, weight=1)
        ttk.Checkbutton(eye_controls, text="Alinear ojos en todo el lote", variable=self.align_eyes_var,
                        command=self.change_eye_alignment).grid(row=0, column=0, sticky="w")
        ttk.Label(eye_controls, text="Ojos al").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Scale(eye_controls, from_=32, to=48, variable=self.eye_position_var,
                  command=self.change_eye_position).grid(row=0, column=2, sticky="ew", padx=(6, 5))
        ttk.Label(eye_controls, textvariable=self.eye_position_text, width=5).grid(row=0, column=3, sticky="w")
        ttk.Label(eye_controls, text="desde arriba del recuadro (40% es un buen punto de partida).").grid(row=0, column=4, sticky="w", padx=(10, 0))

        settings = ttk.LabelFrame(root, text="Salida", padding=10)
        settings.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 5))
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Relación de aspecto:").grid(row=0, column=0, sticky="w", pady=3)
        aspect_box = ttk.Combobox(settings, textvariable=self.aspect_var,
                                  values=[*ASPECT_PRESETS.keys(), "Personalizada"], state="readonly", width=24)
        aspect_box.grid(row=0, column=1, sticky="w", padx=(8, 8), pady=3)
        aspect_box.bind("<<ComboboxSelected>>", lambda _event: self.change_aspect())
        ttk.Label(settings, text="Personalizada (ej. 2:3):").grid(row=0, column=2, sticky="e", pady=3)
        custom_entry = ttk.Entry(settings, textvariable=self.custom_aspect_var, width=10)
        custom_entry.grid(row=0, column=3, sticky="w", padx=(8, 0), pady=3)
        custom_entry.bind("<Return>", lambda _event: self.change_aspect())
        custom_entry.bind("<FocusOut>", lambda _event: self.change_aspect() if self.aspect_var.get() == "Personalizada" else None)

        ttk.Label(settings, text="Carpeta destino:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(settings, textvariable=self.output_dir_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 8), pady=3)
        ttk.Button(settings, text="Elegir…", command=self.choose_output_dir).grid(row=1, column=3, sticky="e", pady=3)

        ttk.Label(settings, text="Formato:").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Combobox(settings, textvariable=self.format_var, values=list(EXPORT_FORMATS), state="readonly", width=10).grid(row=2, column=1, sticky="w", padx=(8, 8), pady=3)
        ttk.Label(settings, text="Sufijo (opcional):").grid(row=2, column=2, sticky="e", pady=3)
        suffix_frame = ttk.Frame(settings)
        suffix_frame.grid(row=2, column=3, sticky="w")
        ttk.Entry(suffix_frame, textvariable=self.suffix_var, width=15).pack(side="left")
        ttk.Label(suffix_frame, text="  ej. _credencial").pack(side="left")

        ttk.Label(settings, text="Tamaño final en px (opcional):").grid(row=3, column=0, sticky="w", pady=3)
        dimensions = ttk.Frame(settings)
        dimensions.grid(row=3, column=1, sticky="w", padx=(8, 8), pady=3)
        ttk.Entry(dimensions, textvariable=self.width_var, width=7).pack(side="left")
        ttk.Label(dimensions, text=" × ").pack(side="left")
        ttk.Entry(dimensions, textvariable=self.height_var, width=7).pack(side="left")

        footer = ttk.Frame(root, padding=(10, 5, 10, 10))
        footer.grid(row=4, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Exportar actual", command=lambda: self.export_photos(False), style="Secondary.TButton").grid(row=0, column=1, padx=(8, 5))
        ttk.Button(footer, text="Exportar todas", command=lambda: self.export_photos(True), style="Success.TButton").grid(row=0, column=2)

    def _build_sidebar(self, sidebar: ttk.Frame) -> None:
        """Panel lateral de controles, para mantener la vista previa despejada."""
        tabs = ttk.Notebook(sidebar)
        tabs.grid(row=0, column=0, sticky="nsew")
        edit_tab = ttk.Frame(tabs, padding=8)
        output_tab = ttk.Frame(tabs, padding=8)
        edit_tab.columnconfigure(0, weight=1)
        output_tab.columnconfigure(0, weight=1)
        tabs.add(edit_tab, text="Editar")
        tabs.add(output_tab, text="Salida")

        crop_controls = ttk.LabelFrame(edit_tab, text="Encuadre", padding=8)
        crop_controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        crop_controls.columnconfigure(0, weight=1)
        crop_controls.columnconfigure(1, weight=1)
        ttk.Button(crop_controls, text="− Alejar", command=lambda: self.zoom_current(1.12), style="Secondary.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 5))
        ttk.Button(crop_controls, text="+ Acercar", command=lambda: self.zoom_current(0.89), style="Secondary.TButton").grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 5))
        ttk.Button(crop_controls, text="Centrar marco", command=self.center_current, style="Secondary.TButton").grid(row=1, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(crop_controls, text="Detectar foto", command=self.auto_crop_current, style="Auto.TButton").grid(row=1, column=1, sticky="ew", padx=(4, 0))

        adjustments = ttk.LabelFrame(edit_tab, text="Ajustes de esta foto", padding=8)
        adjustments.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        adjustments.columnconfigure(0, weight=1)
        ttk.Label(adjustments, text="Brillo").grid(row=0, column=0, sticky="w")
        ttk.Label(adjustments, textvariable=self.brightness_text).grid(row=0, column=1, sticky="e")
        ModernSlider(adjustments, from_=-60, to=60, variable=self.brightness_var,
                     command=self.change_brightness).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Label(adjustments, text="Contraste").grid(row=2, column=0, sticky="w")
        ttk.Label(adjustments, textvariable=self.contrast_text).grid(row=2, column=1, sticky="e")
        ModernSlider(adjustments, from_=-60, to=60, variable=self.contrast_var,
                     command=self.change_contrast, accent="#6c4ba3").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        action_row = ttk.Frame(adjustments)
        action_row.grid(row=4, column=0, columnspan=2, sticky="ew")
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)
        ttk.Button(action_row, text="Auto luz", command=self.auto_adjust_current, style="Auto.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(action_row, text="Restablecer", command=self.reset_adjustments, style="Secondary.TButton").grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Separator(adjustments, orient="horizontal").grid(row=5, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(adjustments, text="Margen superior para cabello").grid(row=6, column=0, sticky="w")
        ttk.Label(adjustments, textvariable=self.hair_margin_text).grid(row=6, column=1, sticky="e")
        ModernSlider(adjustments, from_=8, to=35, variable=self.hair_margin_var,
                     command=self.change_hair_margin, accent="#e17d2f").grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Checkbutton(adjustments, text="Alinear ojos en todo el lote", variable=self.align_eyes_var,
                        command=self.change_eye_alignment).grid(row=8, column=0, columnspan=2, sticky="w")
        ttk.Label(adjustments, text="Ojos desde arriba").grid(row=9, column=0, sticky="w", pady=(5, 0))
        ttk.Label(adjustments, textvariable=self.eye_position_text).grid(row=9, column=1, sticky="e", pady=(5, 0))
        ModernSlider(adjustments, from_=32, to=48, variable=self.eye_position_var,
                     command=self.change_eye_position, accent="#16856f").grid(row=10, column=0, columnspan=2, sticky="ew")

        settings = ttk.LabelFrame(output_tab, text="Salida", padding=8)
        settings.grid(row=2, column=0, sticky="ew")
        settings.columnconfigure(0, weight=1)
        ttk.Label(settings, text="Relación de aspecto").grid(row=0, column=0, sticky="w")
        aspect_box = ttk.Combobox(settings, textvariable=self.aspect_var,
                                  values=[*ASPECT_PRESETS.keys(), "Personalizada"], state="readonly")
        aspect_box.grid(row=1, column=0, sticky="ew", pady=(2, 5))
        aspect_box.bind("<<ComboboxSelected>>", lambda _event: self.change_aspect())
        ttk.Label(settings, text="Personalizada (ej. 2:3)").grid(row=2, column=0, sticky="w")
        custom_entry = ttk.Entry(settings, textvariable=self.custom_aspect_var)
        custom_entry.grid(row=3, column=0, sticky="ew", pady=(2, 5))
        custom_entry.bind("<Return>", lambda _event: self.change_aspect())
        custom_entry.bind("<FocusOut>", lambda _event: self.change_aspect() if self.aspect_var.get() == "Personalizada" else None)
        ttk.Label(settings, text="Carpeta destino").grid(row=4, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.output_dir_var).grid(row=5, column=0, sticky="ew", pady=(2, 4))
        ttk.Button(settings, text="Elegir carpeta…", command=self.choose_output_dir, style="Secondary.TButton").grid(row=6, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(settings, text="Formato").grid(row=7, column=0, sticky="w")
        ttk.Combobox(settings, textvariable=self.format_var, values=list(EXPORT_FORMATS), state="readonly").grid(row=8, column=0, sticky="ew", pady=(2, 5))
        ttk.Label(settings, text="Sufijo opcional (ej. _credencial)").grid(row=9, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.suffix_var).grid(row=10, column=0, sticky="ew", pady=(2, 5))
        ttk.Label(settings, text="Tamaño final en px (opcional)").grid(row=11, column=0, sticky="w")
        dimensions = ttk.Frame(settings)
        dimensions.grid(row=12, column=0, sticky="w", pady=(2, 7))
        ttk.Entry(dimensions, textvariable=self.width_var, width=7).pack(side="left")
        ttk.Label(dimensions, text=" × ").pack(side="left")
        ttk.Entry(dimensions, textvariable=self.height_var, width=7).pack(side="left")
        ttk.Button(settings, text="Exportar actual", command=lambda: self.export_photos(False), style="Secondary.TButton").grid(row=13, column=0, sticky="ew", pady=(0, 5))
        ttk.Button(settings, text="Exportar todas", command=lambda: self.export_photos(True), style="Success.TButton").grid(row=14, column=0, sticky="ew")

    def add_photos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Seleccionar fotos",
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"), ("Todos los archivos", "*.*")],
        )
        self._add_paths(Path(path) for path in paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Seleccionar carpeta con fotos")
        if not folder:
            return
        self._add_paths(path for path in Path(folder).iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)

    def _add_paths(self, paths) -> None:
        existing = {item.path.resolve() for item in self.photos}
        added = 0
        errors: list[str] = []
        for path in paths:
            try:
                path = path.resolve()
                if path in existing or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                with Image.open(path) as source:
                    image = ImageOps.exif_transpose(source).copy()
                w, h = image.size
                self.photos.append(PhotoItem(path, image, self.default_crop(w, h)))
                existing.add(path)
                added += 1
            except (OSError, UnidentifiedImageError) as error:
                errors.append(f"{path.name}: {error}")
        self.rebuild_list()
        if added and self.current_index is None:
            self.select_photo(0)
        if added:
            self.status_var.set(f"Se agregaron {added} foto(s). Usá ‘Detectar y encuadrar todas’ para el encuadre automático.")
        if errors:
            messagebox.showwarning("Fotos no cargadas", "No se pudieron leer:\n" + "\n".join(errors[:5]))

    def rebuild_list(self) -> None:
        selected = self.current_index
        self.photo_list.delete(0, tk.END)
        for item in self.photos:
            marker = "●" if item.face_found else "○"
            self.photo_list.insert(tk.END, f"{marker}  {item.path.name}")
        if selected is not None and selected < len(self.photos):
            self.photo_list.selection_set(selected)

    def on_photo_selected(self, _event=None) -> None:
        selection = self.photo_list.curselection()
        if selection:
            self.current_index = selection[0]
            self.sync_adjustment_controls()
            self.refresh_preview()

    def select_photo(self, index: int) -> None:
        if not self.photos:
            return
        self.current_index = max(0, min(index, len(self.photos) - 1))
        self.photo_list.selection_clear(0, tk.END)
        self.photo_list.selection_set(self.current_index)
        self.photo_list.see(self.current_index)
        self.sync_adjustment_controls()
        self.refresh_preview()

    def remove_current(self) -> None:
        if self.current_index is None:
            return
        del self.photos[self.current_index]
        if not self.photos:
            self.current_index = None
        else:
            self.current_index = min(self.current_index, len(self.photos) - 1)
        self.rebuild_list()
        if self.current_index is not None:
            self.select_photo(self.current_index)
        else:
            self.refresh_preview()
        self.status_var.set("Foto quitada.")

    def clear_photos(self) -> None:
        if self.photos and messagebox.askyesno("Vaciar lista", "¿Quitar todas las fotos de la lista?"):
            self.photos.clear()
            self.current_index = None
            self.rebuild_list()
            self.refresh_preview()
            self.status_var.set("Lista vacía.")

    def get_aspect_ratio(self, show_error: bool = True) -> Optional[float]:
        preset = self.aspect_var.get()
        if preset in ASPECT_PRESETS:
            return ASPECT_PRESETS[preset]
        try:
            value = self.custom_aspect_var.get().strip().replace(" ", "")
            if ":" in value:
                width, height = (float(part) for part in value.split(":", 1))
                ratio = width / height
            else:
                ratio = float(value)
            if ratio <= 0:
                raise ValueError
            return ratio
        except (ValueError, ZeroDivisionError):
            if show_error:
                messagebox.showerror("Relación inválida", "Escribí una relación positiva, por ejemplo 3:4 o 0.75.")
            return None

    def default_crop(self, image_width: int, image_height: int) -> tuple[float, float, float, float]:
        ratio = self.get_aspect_ratio(show_error=False) or 3 / 4
        crop_h = min(image_height, image_width / ratio)
        crop_w = crop_h * ratio
        return ((image_width - crop_w) / 2, (image_height - crop_h) / 2,
                (image_width + crop_w) / 2, (image_height + crop_h) / 2)

    def get_current(self) -> Optional[PhotoItem]:
        if self.current_index is None or self.current_index >= len(self.photos):
            return None
        return self.photos[self.current_index]

    def load_face_cascade(self) -> Optional[cv2.CascadeClassifier]:
        if self._face_cascade is None:
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(str(cascade_path))
            if cascade.empty():
                messagebox.showerror("Detector no disponible", "No se pudo cargar el detector de rostros de OpenCV.")
                return None
            self._face_cascade = cascade
        return self._face_cascade

    def load_eye_cascade(self) -> Optional[cv2.CascadeClassifier]:
        if self._eye_cascade is None:
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_eye_tree_eyeglasses.xml"
            cascade = cv2.CascadeClassifier(str(cascade_path))
            if cascade.empty():
                return None
            self._eye_cascade = cascade
        return self._eye_cascade

    def find_largest_face(self, image: Image.Image) -> Optional[tuple[int, int, int, int]]:
        cascade = self.load_face_cascade()
        if cascade is None:
            return None
        rgb = np.asarray(image.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(36, 36))
        if len(faces) == 0:
            return None
        return max(faces, key=lambda face: face[2] * face[3])

    def find_eye_line(self, image: Image.Image, face: tuple[int, int, int, int]) -> Optional[float]:
        """Devuelve la coordenada vertical promedio de ambos ojos dentro de la foto."""
        cascade = self.load_eye_cascade()
        if cascade is None:
            return None
        face_x, face_y, face_w, face_h = face
        gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        # Los ojos se encuentran en la parte alta de la cara; limitar la búsqueda
        # reduce falsos positivos en nariz, boca o fondo.
        roi_height = max(1, int(face_h * 0.62))
        roi = gray[face_y:face_y + roi_height, face_x:face_x + face_w]
        if roi.size == 0:
            return None
        candidates = cascade.detectMultiScale(
            roi, scaleFactor=1.10, minNeighbors=5,
            minSize=(max(12, int(face_w * 0.12)), max(12, int(face_h * 0.08))),
        )
        centers = [(face_x + x + w / 2, face_y + y + h / 2) for x, y, w, h in candidates]
        best_pair: Optional[tuple[tuple[float, float], tuple[float, float]]] = None
        best_score = float("-inf")
        for index, first in enumerate(centers):
            for second in centers[index + 1:]:
                horizontal = abs(first[0] - second[0])
                vertical = abs(first[1] - second[1])
                if horizontal < face_w * 0.22 or vertical > face_h * 0.16:
                    continue
                score = horizontal - vertical * 1.8
                if score > best_score:
                    best_score, best_pair = score, (first, second)
        if best_pair:
            return (best_pair[0][1] + best_pair[1][1]) / 2
        return None

    def get_eye_line(self, item: PhotoItem) -> Optional[float]:
        if item.eyes_checked:
            return item.eye_line
        item.eyes_checked = True
        if item.face_box:
            item.eye_line = self.find_eye_line(item.image, item.face_box)
        return item.eye_line

    def auto_crop_item(self, item: PhotoItem) -> bool:
        face = item.face_box or self.find_largest_face(item.image)
        if face is None:
            item.crop = self.default_crop(*item.image.size)
            item.face_found = False
            return False
        item.face_box = tuple(int(value) for value in face)
        self.apply_face_crop(item)
        return True

    def apply_face_crop(self, item: PhotoItem) -> None:
        """Crea un encuadre vertical con espacio configurable por encima de la cara."""
        if item.face_box is None:
            return
        ratio = self.get_aspect_ratio(show_error=False) or 3 / 4
        eye_line = self.get_eye_line(item) if self.align_eyes_var.get() else None
        item.crop = compute_face_crop(
            item.image.size, item.face_box, eye_line, item.hair_margin, ratio,
            self.eye_position_var.get(),
        )
        item.face_found = True

    def auto_crop_current(self) -> None:
        item = self.get_current()
        if item is None:
            return
        found = self.auto_crop_item(item)
        self.rebuild_list()
        self.refresh_preview()
        self.status_var.set("Rostro detectado y encuadrado." if found else "No se detectó un rostro; se aplicó un encuadre centrado.")

    def sync_adjustment_controls(self) -> None:
        item = self.get_current()
        if item is None:
            return
        brightness = round((item.brightness - 1) * 100)
        contrast = round((item.contrast - 1) * 100)
        hair_margin = round(item.hair_margin * 100)
        self.brightness_var.set(brightness)
        self.contrast_var.set(contrast)
        self.hair_margin_var.set(hair_margin)
        self.brightness_text.set(f"{brightness:+d}")
        self.contrast_text.set(f"{contrast:+d}")
        self.hair_margin_text.set(f"{hair_margin}%")
        self.eye_position_text.set(f"{round(self.eye_position_var.get())}%")

    def change_brightness(self, value: str) -> None:
        item = self.get_current()
        if item is None:
            return
        adjustment = round(float(value))
        item.brightness = max(0.20, 1 + adjustment / 100)
        self.brightness_text.set(f"{adjustment:+d}")
        self.refresh_preview()

    def change_contrast(self, value: str) -> None:
        item = self.get_current()
        if item is None:
            return
        adjustment = round(float(value))
        item.contrast = max(0.20, 1 + adjustment / 100)
        self.contrast_text.set(f"{adjustment:+d}")
        self.refresh_preview()

    def change_hair_margin(self, value: str) -> None:
        item = self.get_current()
        if item is None:
            return
        margin = round(float(value))
        item.hair_margin = margin / 100
        self.hair_margin_text.set(f"{margin}%")
        if item.face_box:
            self.apply_face_crop(item)
            self.refresh_preview()

    def reframe_detected_faces(self) -> None:
        count = 0
        for item in self.photos:
            if item.face_box:
                self.apply_face_crop(item)
                count += 1
        self.refresh_preview()
        if count:
            self.status_var.set(f"Se actualizó el encuadre de {count} foto(s) con rostro detectado.")

    def change_eye_alignment(self) -> None:
        self.reframe_detected_faces()

    def change_eye_position(self, value: str) -> None:
        position = round(float(value))
        self.eye_position_text.set(f"{position}%")
        self.reframe_detected_faces()

    def reset_adjustments(self) -> None:
        item = self.get_current()
        if item is None:
            return
        item.brightness = 1.0
        item.contrast = 1.0
        self.sync_adjustment_controls()
        self.refresh_preview()

    def auto_adjust_current(self) -> None:
        item = self.get_current()
        if item is None:
            return
        grayscale = ImageOps.grayscale(item.image)
        stats = ImageStat.Stat(grayscale)
        mean, deviation = stats.mean[0], stats.stddev[0]
        # Valores moderados para mejorar una foto oscura o lavada sin sobreprocesarla.
        item.brightness = min(1.40, max(0.72, 128 / max(mean, 1)))
        item.contrast = min(1.45, max(0.80, 55 / max(deviation, 1)))
        self.sync_adjustment_controls()
        self.refresh_preview()
        self.status_var.set("Se aplicó un ajuste automático de brillo y contraste a esta foto.")

    @staticmethod
    def adjusted_image(item: PhotoItem) -> Image.Image:
        image = item.image
        if item.brightness != 1.0:
            image = ImageEnhance.Brightness(image).enhance(item.brightness)
        if item.contrast != 1.0:
            image = ImageEnhance.Contrast(image).enhance(item.contrast)
        return image

    def auto_crop_all(self) -> None:
        if not self.photos:
            messagebox.showinfo("Sin fotos", "Primero agregá una o más fotos.")
            return
        detected = 0
        self.root.config(cursor="watch")
        try:
            for position, item in enumerate(self.photos, start=1):
                self.status_var.set(f"Analizando foto {position} de {len(self.photos)}…")
                self.root.update_idletasks()
                detected += int(self.auto_crop_item(item))
        finally:
            self.root.config(cursor="")
        self.rebuild_list()
        self.refresh_preview()
        self.status_var.set(f"Encuadre automático terminado: {detected} de {len(self.photos)} rostro(s) detectado(s).")

    def change_aspect(self) -> None:
        ratio = self.get_aspect_ratio()
        if ratio is None:
            return
        for item in self.photos:
            left, top, right, bottom = item.crop
            current_w, current_h = right - left, bottom - top
            center_x, center_y = (left + right) / 2, (top + bottom) / 2
            new_h = current_h
            new_w = new_h * ratio
            if new_w > item.image.width:
                new_w = item.image.width
                new_h = new_w / ratio
            if new_h > item.image.height:
                new_h = item.image.height
                new_w = new_h * ratio
            self.set_crop_center(item, center_x, center_y, new_w, new_h)
        self.refresh_preview()
        self.status_var.set(f"Relación de aspecto aplicada: {self.aspect_var.get()}.")

    @staticmethod
    def set_crop_center(item: PhotoItem, center_x: float, center_y: float, width: float, height: float) -> None:
        width = min(width, item.image.width)
        height = min(height, item.image.height)
        left = min(max(0.0, center_x - width / 2), item.image.width - width)
        top = min(max(0.0, center_y - height / 2), item.image.height - height)
        item.crop = (left, top, left + width, top + height)

    def zoom_current(self, factor: float) -> None:
        item = self.get_current()
        if item is None:
            return
        left, top, right, bottom = item.crop
        width, height = right - left, bottom - top
        ratio = self.get_aspect_ratio(show_error=False)
        if ratio is None:
            return
        new_h = max(80.0, height * factor)
        new_w = new_h * ratio
        if new_w > item.image.width:
            new_w = item.image.width
            new_h = new_w / ratio
        if new_h > item.image.height:
            new_h = item.image.height
            new_w = new_h * ratio
        self.set_crop_center(item, (left + right) / 2, (top + bottom) / 2, new_w, new_h)
        self.refresh_preview()

    def center_current(self) -> None:
        item = self.get_current()
        if item is None:
            return
        left, top, right, bottom = item.crop
        self.set_crop_center(item, item.image.width / 2, item.image.height / 2, right - left, bottom - top)
        self.refresh_preview()

    def refresh_preview(self) -> None:
        self.canvas.delete("all")
        item = self.get_current()
        if item is None:
            self.canvas.create_text(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2,
                                    text="Seleccioná una o más fotos para ver la vista previa", fill="#d0d0d0", font=("Segoe UI", 13))
            self.preview_info.configure(text="")
            return
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        image_w, image_h = item.image.size
        scale = min((canvas_w - 24) / image_w, (canvas_h - 24) / image_h)
        display_w, display_h = max(1, int(image_w * scale)), max(1, int(image_h * scale))
        origin_x, origin_y = (canvas_w - display_w) // 2, (canvas_h - display_h) // 2
        preview = self.adjusted_image(item).copy()
        preview.thumbnail((display_w, display_h), Image.Resampling.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(preview)
        self.canvas.create_image(origin_x, origin_y, image=self._preview_photo, anchor="nw")
        self._display_origin = (origin_x, origin_y)
        self._display_scale = preview.width / image_w

        left, top, right, bottom = item.crop
        x1, y1 = origin_x + left * self._display_scale, origin_y + top * self._display_scale
        x2, y2 = origin_x + right * self._display_scale, origin_y + bottom * self._display_scale
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#ffffff", width=3, tags="crop")
        self.canvas.create_rectangle(x1 + 3, y1 + 3, x2 - 3, y2 - 3, outline="#1296db", width=1, tags="crop")
        alignment = "ojos alineados" if self.align_eyes_var.get() and item.eye_line is not None else "posición facial estimada"
        self.preview_info.configure(text=f"{item.image.width} × {item.image.height} px  |  {alignment if item.face_found else 'encuadre manual/centrado'}")

    def start_drag(self, event) -> None:
        item = self.get_current()
        if item is None:
            return
        left, top, right, bottom = item.crop
        origin_x, origin_y = self._display_origin
        x1, y1 = origin_x + left * self._display_scale, origin_y + top * self._display_scale
        x2, y2 = origin_x + right * self._display_scale, origin_y + bottom * self._display_scale
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            self._drag_start = (event.x, event.y, item.crop)

    def drag_crop(self, event) -> None:
        item = self.get_current()
        if item is None or self._drag_start is None:
            return
        start_x, start_y, start_crop = self._drag_start
        dx = (event.x - start_x) / self._display_scale
        dy = (event.y - start_y) / self._display_scale
        left, top, right, bottom = start_crop
        self.set_crop_center(item, (left + right) / 2 + dx, (top + bottom) / 2 + dy, right - left, bottom - top)
        self.refresh_preview()

    def end_drag(self, _event) -> None:
        self._drag_start = None

    def choose_output_dir(self) -> None:
        folder = filedialog.askdirectory(title="Elegir carpeta de salida")
        if folder:
            self.output_dir_var.set(folder)

    def get_output_size(self, crop: tuple[float, float, float, float]) -> Optional[tuple[int, int]]:
        width_text, height_text = self.width_var.get().strip(), self.height_var.get().strip()
        if not width_text and not height_text:
            return None
        try:
            crop_w, crop_h = crop[2] - crop[0], crop[3] - crop[1]
            if width_text and height_text:
                width, height = int(width_text), int(height_text)
            elif width_text:
                width = int(width_text)
                height = round(width * crop_h / crop_w)
            else:
                height = int(height_text)
                width = round(height * crop_w / crop_h)
            if width < 1 or height < 1:
                raise ValueError
            return width, height
        except ValueError:
            messagebox.showerror("Tamaño inválido", "Escribí valores enteros positivos para el tamaño final.")
            return None

    def export_photos(self, export_all: bool) -> None:
        if not self.photos:
            messagebox.showinfo("Sin fotos", "No hay fotos para exportar.")
            return
        if not self.output_dir_var.get().strip():
            self.choose_output_dir()
            if not self.output_dir_var.get().strip():
                return
        output_dir = Path(self.output_dir_var.get()).expanduser()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            messagebox.showerror("Carpeta no disponible", f"No se puede crear la carpeta de salida:\n{error}")
            return
        items = self.photos if export_all else ([self.get_current()] if self.get_current() else [])
        if not items:
            return
        extension, pil_format = EXPORT_FORMATS[self.format_var.get()]
        suffix = self.suffix_var.get().strip()
        saved = 0
        try:
            for number, item in enumerate(items, start=1):
                size = self.get_output_size(item.crop)
                if (self.width_var.get().strip() or self.height_var.get().strip()) and size is None:
                    return
                box = tuple(round(value) for value in item.crop)
                image = self.adjusted_image(item).crop(box)
                if size:
                    image = image.resize(size, Image.Resampling.LANCZOS)
                destination = output_dir / f"{item.path.stem}{suffix}{extension}"
                if pil_format == "JPEG":
                    if image.mode in ("RGBA", "LA"):
                        background = Image.new("RGB", image.size, "white")
                        background.paste(image, mask=image.getchannel("A"))
                        image = background
                    else:
                        image = image.convert("RGB")
                    image.save(destination, pil_format, quality=95, optimize=True)
                elif pil_format == "WEBP":
                    image.save(destination, pil_format, quality=95, method=6)
                elif pil_format == "PNG":
                    image.save(destination, pil_format, optimize=True)
                else:
                    image.save(destination, pil_format)
                saved += 1
                self.status_var.set(f"Exportando {number} de {len(items)}…")
                self.root.update_idletasks()
        except OSError as error:
            messagebox.showerror("Error al exportar", f"No se pudo guardar la imagen:\n{error}")
            return
        self.status_var.set(f"Listo: se exportaron {saved} foto(s) en {output_dir}.")
        messagebox.showinfo("Exportación terminada", f"Se exportaron {saved} foto(s) en:\n{output_dir}")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    FaceCropperApp().run()
