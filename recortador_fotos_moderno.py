"""Prototipo visual moderno del recortador de fotos.

Mantiene el procesamiento local de la versión original y reemplaza solamente
la interfaz por CustomTkinter.
"""

from __future__ import annotations

import json
import os
import re
import csv
from datetime import date
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageOps, ImageTk, UnidentifiedImageError

import face_detection
from recortador_fotos import (
    ASPECT_PRESETS,
    EXPORT_FORMATS,
    IMAGE_FILE_PATTERN,
    JPEG_QUALITY,
    SUPPORTED_EXTENSIONS,
    FaceCropperApp,
    PhotoItem,
)


class RecortadorModerno(FaceCropperApp):
    SECONDARY = ("#e6f0f7", "#2d4353")
    SECONDARY_HOVER = ("#d4e5f1", "#3a566a")
    SECONDARY_TEXT = ("#164f75", "#d9ecf8")
    PURPLE = ("#744fa8", "#8a67bc")
    PURPLE_HOVER = ("#5d3e8b", "#7453a1")
    DANGER = ("#fbe8e8", "#57343a")
    DANGER_HOVER = ("#f5d5d5", "#704148")
    DANGER_TEXT = ("#a53a3a", "#ffb6b6")
    MUTED = ("#607587", "#aebdca")
    TEXT = ("#26364a", "#e1e8ee")
    DEFAULT_PRESETS = {
        "Credencial estándar": {"aspect": "3:4 (identificación)", "custom_aspect": "3:4", "hair_margin": 20, "align_eyes": True, "eye_position": 40, "format": "JPG", "width": "600", "height": "800", "template": "{nombre}{sufijo}"},
        "Foto documento": {"aspect": "35 × 45 mm (documento)", "custom_aspect": "35:45", "hair_margin": 24, "align_eyes": True, "eye_position": 40, "format": "JPG", "width": "600", "height": "771", "template": "{nombre}{sufijo}"},
    }

    def __init__(self) -> None:
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk()
        self.root.title("Recortador de fotos · moderno")
        self.root.geometry("1360x840")
        self.root.minsize(1080, 680)

        self.photos: list[PhotoItem] = []
        self.current_index: Optional[int] = None
        self._preview_photo: Optional[ImageTk.PhotoImage] = None
        self._display_origin = (0, 0)
        self._display_scale = 1.0
        self._drag_start = None
        self.show_original = False
        self.visible_indices: list[int] = []
        self.history: dict[str, list[dict]] = {}

        self.aspect_var = tk.StringVar(value="3:4 (identificación)")
        self.custom_aspect_var = tk.StringVar(value="3:4")
        self.output_dir_var = tk.StringVar()
        self.format_var = tk.StringVar(value="JPG")
        self.suffix_var = tk.StringVar()
        self.name_template_var = tk.StringVar(value="{nombre}{sufijo}")
        self.brightness_var = tk.DoubleVar(value=0)
        self.contrast_var = tk.DoubleVar(value=0)
        self.hair_margin_var = tk.DoubleVar(value=20)
        self.align_eyes_var = tk.BooleanVar(value=True)
        self.eye_position_var = tk.DoubleVar(value=40)
        self.detector_var = tk.StringVar(value=face_detection.detector_preference_label())
        self.brightness_text = tk.StringVar(value="+0")
        self.contrast_text = tk.StringVar(value="+0")
        self.hair_margin_text = tk.StringVar(value="20%")
        self.eye_position_text = tk.StringVar(value="40%")
        self.width_var = tk.StringVar(value="600")
        self.height_var = tk.StringVar(value="800")
        self.status_var = tk.StringVar(value="Agregá fotos para comenzar.")
        self.preset_var = tk.StringVar(value="Credencial estándar")
        self.preset_name_var = tk.StringVar()
        self.presets = self._load_presets()
        session = self._load_session()
        self.output_dir_var.set(session.get("output_dir", ""))
        self.last_input_dir = session.get("input_dir", "")
        self.filter_review_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._bind_shortcuts()

    @property
    def preset_path(self) -> Path:
        base = Path(os.environ.get("APPDATA", Path.home())) / "RecortadorFotos"
        base.mkdir(parents=True, exist_ok=True)
        return base / "presets.json"

    def _load_presets(self) -> dict:
        presets = dict(self.DEFAULT_PRESETS)
        try:
            saved = json.loads(self.preset_path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                presets.update(saved)
        except (OSError, json.JSONDecodeError):
            pass
        return presets

    def _save_presets(self) -> None:
        custom = {name: data for name, data in self.presets.items() if name not in self.DEFAULT_PRESETS}
        self.preset_path.write_text(json.dumps(custom, indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def session_path(self) -> Path:
        return self.preset_path.with_name("session.json")

    def _load_session(self) -> dict:
        try:
            return json.loads(self.session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_session(self) -> None:
        self.session_path.write_text(json.dumps({"input_dir": self.last_input_dir, "output_dir": self.output_dir_var.get()}, ensure_ascii=False), encoding="utf-8")

    def _build_ui(self) -> None:
        root = self.root
        root.grid_columnconfigure(0, minsize=240)
        root.grid_columnconfigure(1, weight=1)
        root.grid_columnconfigure(2, minsize=340)
        root.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(root, fg_color=("#0c5e91", "#0d405e"), corner_radius=0, height=78)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Recortador de fotos", font=ctk.CTkFont(size=25, weight="bold"), text_color="white").grid(row=0, column=0, sticky="w", padx=22, pady=(12, 0))
        ctk.CTkLabel(header, text="Versión visual · ajustes individuales · procesamiento local", font=ctk.CTkFont(size=13), text_color="#d7ecfa").grid(row=1, column=0, sticky="w", padx=22, pady=(0, 12))
        self.theme_button = ctk.CTkButton(header, text="Modo oscuro", width=115, fg_color=("#287cae", "#236589"), hover_color=("#1b6d9f", "#1b526f"), command=self.toggle_theme)
        self.theme_button.grid(row=0, column=1, rowspan=2, padx=18)

        toolbar = ctk.CTkFrame(root, fg_color="transparent", height=58)
        toolbar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(9, 4))
        ctk.CTkButton(toolbar, text="+  Agregar fotos", command=self.add_photos, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 7))
        ctk.CTkButton(toolbar, text="Agregar carpeta", command=self.add_folder, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Quitar", command=self.remove_current, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER, width=80).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Vaciar", command=self.clear_photos, fg_color=self.DANGER, text_color=self.DANGER_TEXT, hover_color=self.DANGER_HOVER, width=80).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Detectar y encuadrar todas", command=self.auto_crop_all, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).pack(side="left", padx=(14, 0))

        left = ctk.CTkFrame(root, fg_color=("#ffffff", "#202329"), corner_radius=12)
        left.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=(4, 10))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text="Fotos del lote", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 5))
        list_actions = ctk.CTkFrame(left, fg_color="transparent")
        list_actions.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        list_actions.grid_columnconfigure(0, weight=1)
        self.review_count_label = ctk.CTkLabel(list_actions, text="0 listas · 0 para revisar", text_color="#6b7f90", font=ctk.CTkFont(size=11))
        self.review_count_label.grid(row=0, column=0, sticky="w")
        ctk.CTkCheckBox(list_actions, text="Sólo revisar", variable=self.filter_review_var, command=self.rebuild_list, width=90).grid(row=0, column=1, sticky="e")
        self.photo_list_container = ctk.CTkScrollableFrame(left, fg_color="transparent", corner_radius=0)
        self.photo_list_container.grid(row=2, column=0, sticky="nsew", padx=7, pady=(0, 5))
        self.list_hint = ctk.CTkLabel(left, text="✓ listo · ⚠ revisar", text_color="#6b7f90", font=ctk.CTkFont(size=11))
        self.list_hint.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 10))

        center = ctk.CTkFrame(root, fg_color=("#ffffff", "#202329"), corner_radius=12)
        center.grid(row=2, column=1, sticky="nsew", padx=6, pady=(4, 10))
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)
        title_row = ctk.CTkFrame(center, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        title_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(title_row, text="Vista previa", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w")
        self.comparison_button = ctk.CTkButton(title_row, text="Ver original", width=108, height=28, command=self.toggle_comparison, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER)
        self.comparison_button.grid(row=0, column=1, sticky="e")
        self.canvas = tk.Canvas(center, background="#1e2935", highlightthickness=0, cursor="fleur")
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=12)
        self.canvas.bind("<Configure>", lambda _event: self.refresh_preview())
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag_crop)
        self.canvas.bind("<ButtonRelease-1>", self.end_drag)
        self.preview_info = ctk.CTkLabel(center, text="", text_color=self.MUTED, font=ctk.CTkFont(size=12))
        self.preview_info.grid(row=2, column=0, sticky="w", padx=12, pady=(5, 10))

        self.tabs = ctk.CTkTabview(root, corner_radius=12)
        self.tabs.grid(row=2, column=2, sticky="nsew", padx=(6, 12), pady=(4, 10))
        edit = self.tabs.add("Editar")
        output = self.tabs.add("Salida")
        output_scroll = ctk.CTkScrollableFrame(output, fg_color=("#f6f8fa", "#2b2f35"), corner_radius=0,
                                                scrollbar_button_color=("#a9bdcc", "#667786"),
                                                scrollbar_button_hover_color=("#8faabd", "#8495a3"))
        output_scroll.pack(fill="both", expand=True, padx=2, pady=2)
        output_scroll._parent_canvas.bind("<Shift-MouseWheel>", lambda _event: "break")
        output_scroll._parent_canvas.bind("<Configure>", lambda _event: output_scroll._parent_canvas.xview_moveto(0), add="+")
        self._build_edit_tab(edit)
        self._build_output_tab(output_scroll)

        footer = ctk.CTkFrame(root, fg_color="transparent", height=28)
        footer.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 8))
        ctk.CTkLabel(footer, textvariable=self.status_var, text_color=self.MUTED, anchor="w").pack(fill="x")

    def _build_edit_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=4, pady=3)
        for column in range(2):
            frame.grid_columnconfigure(column, weight=1)
        ctk.CTkButton(frame, text="− Alejar", command=lambda: self.zoom_current(1.12), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 7))
        ctk.CTkButton(frame, text="+ Acercar", command=lambda: self.zoom_current(0.89), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 7))
        ctk.CTkButton(frame, text="↺ Rotar izquierda", command=lambda: self.rotate_current(90), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(0, 7))
        ctk.CTkButton(frame, text="Rotar derecha ↻", command=lambda: self.rotate_current(-90), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(0, 7))
        ctk.CTkButton(frame, text="Detectar y encuadrar esta foto", command=self.auto_crop_current, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self._slider(frame, "Brillo", self.brightness_var, self.brightness_text, -60, 60, self.change_brightness, "#1682c2", 3)
        self._slider(frame, "Contraste", self.contrast_var, self.contrast_text, -60, 60, self.change_contrast, "#744fa8", 5)
        ctk.CTkButton(frame, text="Auto luz", command=self.auto_adjust_current, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=7, column=0, sticky="ew", padx=(0, 4), pady=(3, 12))
        ctk.CTkButton(frame, text="Restablecer", command=self.reset_adjustments, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=7, column=1, sticky="ew", padx=(4, 0), pady=(3, 12))
        self._slider(frame, "Margen para cabello", self.hair_margin_var, self.hair_margin_text, 8, 35, self.change_hair_margin, "#e07b2d", 8)
        self.align_check = ctk.CTkCheckBox(frame, text="Alinear ojos en todo el lote", variable=self.align_eyes_var, command=self.change_eye_alignment)
        self.align_check.grid(row=10, column=0, columnspan=2, sticky="w", pady=(9, 0))
        self._slider(frame, "Ojos desde arriba", self.eye_position_var, self.eye_position_text, 32, 48, self.change_eye_position, "#16856f", 11)
        ctk.CTkButton(frame, text="Deshacer última acción", command=self.undo_current, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=13, column=0, sticky="ew", padx=(0, 4), pady=(10, 0))
        ctk.CTkButton(frame, text="Copiar ajustes al lote", command=self.copy_adjustments_to_all, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=13, column=1, sticky="ew", padx=(4, 0), pady=(10, 0))
        ctk.CTkLabel(frame, text="Detector", fg_color="transparent", text_color=self.TEXT).grid(row=14, column=0, columnspan=2, sticky="w", pady=(12, 2))
        self.detector_menu = ctk.CTkOptionMenu(
            frame,
            values=list(face_detection.DETECTOR_LABELS),
            variable=self.detector_var,
            command=lambda _value: self.change_detector(),
        )
        self.detector_menu.grid(row=15, column=0, columnspan=2, sticky="ew")

    def _slider(self, parent, label, variable, value_text, minimum, maximum, command, color, row) -> None:
        ctk.CTkLabel(parent, text=label, fg_color="transparent", text_color=self.TEXT).grid(row=row, column=0, sticky="w")
        ctk.CTkLabel(parent, textvariable=value_text, fg_color="transparent", text_color=self.TEXT).grid(row=row, column=1, sticky="e")
        slider = ctk.CTkSlider(parent, from_=minimum, to=maximum, variable=variable, command=command, button_color=color, progress_color=color)
        slider.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        slider.bind("<ButtonPress-1>", lambda _event: self.snapshot_current(), add="+")

    def _build_output_tab(self, tab) -> None:
        tab.grid_columnconfigure(0, weight=1)
        def label(text, row): ctk.CTkLabel(tab, text=text, fg_color="transparent", text_color=self.TEXT).grid(row=row, column=0, sticky="w", padx=8, pady=(7, 1))
        preset_info = ctk.CTkFrame(tab, fg_color=("#eaf4fb", "#253948"), corner_radius=8)
        preset_info.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        ctk.CTkLabel(preset_info, text="Se guarda en el preset", font=ctk.CTkFont(size=12, weight="bold"), text_color=("#176898", "#84c8ee")).pack(anchor="w", padx=9, pady=(7, 0))
        ctk.CTkLabel(preset_info, text="Proporción, cabello, ojos, formato, tamaño y plantilla de nombre.", wraplength=275, justify="left", anchor="w", fg_color="transparent", text_color=self.TEXT, font=ctk.CTkFont(size=11)).pack(fill="x", anchor="w", padx=9, pady=(1, 7))
        lot_info = ctk.CTkFrame(tab, fg_color=("#f5f7f9", "#2b2f35"), corner_radius=8)
        lot_info.grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 3))
        ctk.CTkLabel(lot_info, text="Sólo para este lote", font=ctk.CTkFont(size=12, weight="bold"), text_color=("#65798a", "#c1ccd5")).pack(anchor="w", padx=9, pady=(7, 0))
        ctk.CTkLabel(lot_info, text="Carpeta de destino, sufijo, fotos cargadas y ajustes individuales.", wraplength=275, justify="left", anchor="w", fg_color="transparent", text_color=self.TEXT, font=ctk.CTkFont(size=11)).pack(fill="x", anchor="w", padx=9, pady=(1, 7))
        label("Preset", 2)
        self.preset_menu = ctk.CTkOptionMenu(tab, values=list(self.presets), variable=self.preset_var, command=lambda _value: self.apply_preset())
        self.preset_menu.grid(row=3, column=0, sticky="ew", padx=8)
        self.preset_name_entry = ctk.CTkEntry(tab, textvariable=self.preset_name_var, placeholder_text="Nombre para guardar preset")
        self.preset_name_entry.grid(row=4, column=0, sticky="ew", padx=8, pady=(6, 3))
        preset_buttons = ctk.CTkFrame(tab, fg_color="transparent")
        preset_buttons.grid(row=5, column=0, sticky="ew", padx=8)
        preset_buttons.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(preset_buttons, text="Guardar preset", command=self.save_preset, height=29).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(preset_buttons, text="Aplicar al lote", command=self.apply_preset_to_all, height=29, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ctk.CTkButton(tab, text="Eliminar preset seleccionado", command=self.delete_preset, height=27, fg_color="transparent", text_color=self.DANGER_TEXT, hover_color=self.DANGER_HOVER).grid(row=6, column=0, sticky="w", padx=8)
        label("Relación de aspecto", 7)
        self.aspect_menu = ctk.CTkOptionMenu(tab, values=[*ASPECT_PRESETS, "Personalizada"], variable=self.aspect_var, command=lambda _value: self.change_aspect())
        self.aspect_menu.grid(row=8, column=0, sticky="ew", padx=8)
        self.custom_entry = ctk.CTkEntry(tab, textvariable=self.custom_aspect_var, placeholder_text="Relación personalizada, ej. 2:3")
        self.custom_entry.grid(row=9, column=0, sticky="ew", padx=8, pady=(5, 0))
        self.custom_entry.bind("<Return>", lambda _event: self.change_aspect())
        label("Carpeta destino", 10)
        ctk.CTkEntry(tab, textvariable=self.output_dir_var).grid(row=11, column=0, sticky="ew", padx=8)
        ctk.CTkButton(tab, text="Elegir carpeta", command=self.choose_output_dir, height=29, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=12, column=0, sticky="ew", padx=8, pady=(4, 0))
        label("Formato", 13)
        ctk.CTkOptionMenu(tab, values=list(EXPORT_FORMATS), variable=self.format_var).grid(row=14, column=0, sticky="ew", padx=8)
        label("Nombre de archivo", 15)
        ctk.CTkEntry(tab, textvariable=self.name_template_var).grid(row=16, column=0, sticky="ew", padx=8)
        ctk.CTkLabel(tab, text="Usá {nombre}, {sufijo} o {fecha}", text_color=("#6b7f90", "#aebdca"), font=ctk.CTkFont(size=11)).grid(row=17, column=0, sticky="w", padx=8)
        ctk.CTkEntry(tab, textvariable=self.suffix_var, placeholder_text="Sufijo opcional, ej. _credencial").grid(row=18, column=0, sticky="ew", padx=8, pady=(5, 0))
        dimensions = ctk.CTkFrame(tab, fg_color="transparent")
        dimensions.grid(row=19, column=0, sticky="w", padx=8, pady=(7, 4))
        ctk.CTkLabel(dimensions, text="Tamaño final (automático):", fg_color="transparent", text_color=self.TEXT).pack(side="left", padx=(0, 5))
        ctk.CTkEntry(dimensions, textvariable=self.width_var, width=65, placeholder_text="Ancho").pack(side="left")
        ctk.CTkLabel(dimensions, text=" × ").pack(side="left")
        ctk.CTkEntry(dimensions, textvariable=self.height_var, width=65, placeholder_text="Alto").pack(side="left")
        ctk.CTkButton(tab, text="Exportar actual", command=lambda: self.export_photos(False), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=20, column=0, sticky="ew", padx=8, pady=(6, 4))
        ctk.CTkButton(tab, text="Exportar todas", command=lambda: self.export_photos(True), fg_color=("#11806a", "#218c78"), hover_color=("#0c6655", "#176c5c"), font=ctk.CTkFont(weight="bold")).grid(row=21, column=0, sticky="ew", padx=8)
        ctk.CTkButton(tab, text="Exportar reporte de revisión", command=self.export_review_report, fg_color="transparent", text_color=("#176898", "#84c8ee"), hover_color=("#e8f2f8", "#293d4b")).grid(row=22, column=0, sticky="ew", padx=8, pady=(5, 0))

    def toggle_theme(self) -> None:
        dark = ctk.get_appearance_mode() == "Dark"
        ctk.set_appearance_mode("light" if dark else "dark")
        self.theme_button.configure(text="Modo oscuro" if dark else "Modo claro")

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Left>", lambda event: self._handle_arrow_shortcut(event, -1))
        self.root.bind_all("<Right>", lambda event: self._handle_arrow_shortcut(event, 1))
        self.root.bind("<plus>", lambda _event: self.zoom_current(0.89))
        self.root.bind("<minus>", lambda _event: self.zoom_current(1.12))
        self.root.bind("<r>", lambda _event: self.reset_adjustments())
        self.root.bind("<R>", lambda _event: self.reset_adjustments())

    @staticmethod
    def _event_from_text_input(event) -> bool:
        widget = getattr(event, "widget", None)
        while widget is not None:
            try:
                widget_class = widget.winfo_class()
            except tk.TclError:
                return False
            if widget_class in {"Entry", "TEntry", "Text", "Spinbox", "TSpinbox"}:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _handle_arrow_shortcut(self, event, step: int):
        if self._event_from_text_input(event):
            return None
        self.move_photo(step)
        return "break"

    def move_photo(self, step: int) -> None:
        if self.photos:
            self.select_photo((self.current_index or 0) + step)

    def needs_review(self, item: PhotoItem) -> bool:
        left, top, right, bottom = item.crop
        touches_edge = left <= 1 or top <= 1 or right >= item.image.width - 1 or bottom >= item.image.height - 1
        missing_eyes = self.align_eyes_var.get() and item.face_found and item.eye_line is None
        return not item.face_found or touches_edge or missing_eyes

    def add_photos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Seleccionar fotos", initialdir=self.last_input_dir or None,
            filetypes=[("Imágenes", IMAGE_FILE_PATTERN), ("Todos", "*.*")],
        )
        if paths:
            self.last_input_dir = str(Path(paths[0]).parent)
            self._save_session()
            self._add_paths(Path(path) for path in paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Seleccionar carpeta con fotos", initialdir=self.last_input_dir or None)
        if folder:
            self.last_input_dir = folder
            self._save_session()
            self._add_paths(path for path in Path(folder).iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)

    def choose_output_dir(self) -> None:
        folder = filedialog.askdirectory(title="Elegir carpeta de salida", initialdir=self.output_dir_var.get() or self.last_input_dir or None)
        if folder:
            self.output_dir_var.set(folder)
            self._save_session()

    def rebuild_list(self) -> None:
        for widget in self.photo_list_container.winfo_children():
            widget.destroy()
        self.visible_indices = [index for index, item in enumerate(self.photos) if not self.filter_review_var.get() or self.needs_review(item)]
        pending = sum(self.needs_review(item) for item in self.photos)
        self.review_count_label.configure(text=f"{len(self.photos) - pending} listas · {pending} para revisar")
        self._photo_buttons = {}
        for index in self.visible_indices:
            item = self.photos[index]
            review = self.needs_review(item)
            selected = index == self.current_index
            button = ctk.CTkButton(
                self.photo_list_container, anchor="w",
                text=f"{'⚠' if review else '✓'}  {item.path.name}", height=38,
                fg_color="#1b78b4" if selected else ("#fff4e6" if review else "transparent"),
                text_color="white" if selected else ("#9a5413" if review else ("#31485b", "#e5ebf0")),
                hover_color="#dbeaf4" if not selected else "#15669b",
                command=lambda chosen=index: self.select_photo(chosen),
            )
            button.pack(fill="x", padx=2, pady=2)
            self._photo_buttons[index] = button

    def update_selection_style(self) -> None:
        for index, button in getattr(self, "_photo_buttons", {}).items():
            item = self.photos[index]
            review = self.needs_review(item)
            selected = index == self.current_index
            button.configure(
                fg_color="#1b78b4" if selected else ("#fff4e6" if review else "transparent"),
                text_color="white" if selected else ("#9a5413" if review else ("#31485b", "#e5ebf0")),
                hover_color="#dbeaf4" if not selected else "#15669b",
            )

    def select_photo(self, index: int) -> None:
        if not self.photos:
            return
        self.current_index = max(0, min(index, len(self.photos) - 1))
        self.sync_adjustment_controls()
        self.update_selection_style()
        self.refresh_preview()

    def on_photo_selected(self, _event=None) -> None:
        # La lista moderna usa botones con miniatura; se mantiene por compatibilidad.
        return

    def snapshot_current(self) -> None:
        item = self.get_current()
        if item is None:
            return
        self.snapshot_item(item)

    def snapshot_item(self, item: PhotoItem) -> None:
        history = self.history.setdefault(str(item.path), [])
        history.append({"image": item.image.copy(), "crop": item.crop, "face_found": item.face_found, "face_box": item.face_box, "eye_line": item.eye_line, "eyes_checked": item.eyes_checked, "hair_margin": item.hair_margin, "brightness": item.brightness, "contrast": item.contrast})
        del history[:-12]

    def undo_current(self) -> None:
        item = self.get_current()
        history = self.history.get(str(item.path)) if item else None
        if not item or not history:
            self.status_var.set("No hay acciones para deshacer en esta foto.")
            return
        state = history.pop()
        for key, value in state.items():
            setattr(item, key, value)
        self.sync_adjustment_controls()
        self.rebuild_list()
        self.refresh_preview()
        self.status_var.set("Se deshizo la última acción de esta foto.")

    def copy_adjustments_to_all(self) -> None:
        item = self.get_current()
        if item is None or len(self.photos) < 2:
            return
        if not messagebox.askyesno("Copiar ajustes", "¿Copiar brillo, contraste y margen de cabello a todas las demás fotos?"):
            return
        for target in self.photos:
            if target is item:
                continue
            self.history.setdefault(str(target.path), []).append({"image": target.image.copy(), "crop": target.crop, "face_found": target.face_found, "face_box": target.face_box, "eye_line": target.eye_line, "eyes_checked": target.eyes_checked, "hair_margin": target.hair_margin, "brightness": target.brightness, "contrast": target.contrast})
            target.brightness, target.contrast, target.hair_margin = item.brightness, item.contrast, item.hair_margin
            if target.face_box:
                self.apply_face_crop(target)
        self.rebuild_list()
        self.refresh_preview()
        self.status_var.set("Ajustes copiados al resto del lote.")

    def rotate_current(self, degrees: int) -> None:
        item = self.get_current()
        if item is None:
            return
        self.snapshot_current()
        item.image = ImageOps.exif_transpose(item.image).rotate(degrees, expand=True)
        item.crop = self.default_crop(*item.image.size)
        item.face_found = False
        item.face_box = None
        item.eye_line = None
        item.eyes_checked = False
        self.rebuild_list()
        self.refresh_preview()
        self.status_var.set("Foto rotada. Usá ‘Detectar y encuadrar esta foto’ para recalcular el rostro.")

    def auto_crop_current(self) -> None:
        if self.get_current():
            self.snapshot_current()
        super().auto_crop_current()

    def auto_adjust_current(self) -> None:
        if self.get_current():
            self.snapshot_current()
        super().auto_adjust_current()

    def reset_adjustments(self) -> None:
        if self.get_current():
            self.snapshot_current()
        super().reset_adjustments()

    def toggle_comparison(self) -> None:
        self.show_original = not self.show_original
        self.comparison_button.configure(text="Ver resultado" if self.show_original else "Ver original")
        self.refresh_preview()

    def start_drag(self, event) -> None:
        if not self.show_original:
            self.snapshot_current()
            super().start_drag(event)

    def refresh_preview(self) -> None:
        self.canvas.delete("all")
        item = self.get_current()
        if item is None:
            self.canvas.create_text(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2, text="Agregá fotos para comenzar", fill="#d7e2ec", font=("Segoe UI", 14))
            self.preview_info.configure(text="")
            return
        canvas_w, canvas_h = max(self.canvas.winfo_width(), 1), max(self.canvas.winfo_height(), 1)
        image = item.image if self.show_original else self.adjusted_image(item)
        image_w, image_h = image.size
        scale = min((canvas_w - 24) / image_w, (canvas_h - 24) / image_h)
        display_w, display_h = max(1, int(image_w * scale)), max(1, int(image_h * scale))
        origin_x, origin_y = (canvas_w - display_w) // 2, (canvas_h - display_h) // 2
        preview = image.copy()
        preview.thumbnail((display_w, display_h), Image.Resampling.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(preview)
        self.canvas.create_image(origin_x, origin_y, image=self._preview_photo, anchor="nw")
        self._display_origin, self._display_scale = (origin_x, origin_y), preview.width / image_w
        left, top, right, bottom = item.crop
        x1, y1 = origin_x + left * self._display_scale, origin_y + top * self._display_scale
        x2, y2 = origin_x + right * self._display_scale, origin_y + bottom * self._display_scale
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#ffffff", width=3)
        self.canvas.create_rectangle(x1 + 3, y1 + 3, x2 - 3, y2 - 3, outline="#37aee2", width=1)
        state = "Original" if self.show_original else "Resultado con ajustes"
        review = " · revisar" if self.needs_review(item) else " · listo"
        self.preview_info.configure(text=f"{state} · {item.image.width} × {item.image.height} px{review}")

    def apply_preset(self) -> None:
        preset = self.presets.get(self.preset_var.get())
        if not preset:
            return
        self.aspect_var.set(preset.get("aspect", self.aspect_var.get()))
        self.custom_aspect_var.set(preset.get("custom_aspect", self.custom_aspect_var.get()))
        self.hair_margin_var.set(preset.get("hair_margin", 20))
        self.align_eyes_var.set(preset.get("align_eyes", True))
        self.eye_position_var.set(preset.get("eye_position", 40))
        self.format_var.set(preset.get("format", "JPG"))
        self.width_var.set(preset.get("width", ""))
        self.height_var.set(preset.get("height", ""))
        self.name_template_var.set(preset.get("template", "{nombre}{sufijo}"))
        current = self.get_current()
        if current:
            current.hair_margin = self.hair_margin_var.get() / 100
        self.sync_adjustment_controls()
        self.change_aspect(auto_size=False)
        self.status_var.set(f"Preset aplicado: {self.preset_var.get()}.")

    def apply_preset_to_all(self) -> None:
        if not self.photos:
            self.apply_preset()
            return
        if not messagebox.askyesno("Aplicar al lote", "Esto reencuadrará todas las fotos usando el preset seleccionado. ¿Continuar?"):
            return
        self.apply_preset()
        margin = self.hair_margin_var.get() / 100
        for item in self.photos:
            self.snapshot_item(item)
            item.hair_margin = margin
            self.auto_crop_item(item)
        self.rebuild_list()
        self.refresh_preview()
        self.status_var.set(f"Preset aplicado y recorte actualizado en {len(self.photos)} foto(s).")

    def save_preset(self) -> None:
        name = self.preset_name_var.get().strip()
        if not name:
            messagebox.showinfo("Nombre requerido", "Escribí un nombre para guardar el preset.")
            return
        self.presets[name] = {"aspect": self.aspect_var.get(), "custom_aspect": self.custom_aspect_var.get(), "hair_margin": self.hair_margin_var.get(), "align_eyes": self.align_eyes_var.get(), "eye_position": self.eye_position_var.get(), "format": self.format_var.get(), "width": self.width_var.get(), "height": self.height_var.get(), "template": self.name_template_var.get()}
        self._save_presets()
        self.preset_menu.configure(values=list(self.presets))
        self.preset_var.set(name)
        self.preset_name_var.set("")
        self.status_var.set(f"Preset guardado: {name}.")

    def delete_preset(self) -> None:
        name = self.preset_var.get()
        if name in self.DEFAULT_PRESETS:
            messagebox.showinfo("Preset base", "Los presets incluidos no se pueden eliminar.")
            return
        if name in self.presets and messagebox.askyesno("Eliminar preset", f"¿Eliminar ‘{name}’?"):
            del self.presets[name]
            self._save_presets()
            self.preset_menu.configure(values=list(self.presets))
            self.preset_var.set("Credencial estándar")

    def export_review_report(self) -> None:
        pending = [(index + 1, item) for index, item in enumerate(self.photos) if self.needs_review(item)]
        if not pending:
            messagebox.showinfo("Sin pendientes", "No hay fotos marcadas para revisión.")
            return
        folder = Path(self.output_dir_var.get()) if self.output_dir_var.get().strip() else self.preset_path.parent
        try:
            folder.mkdir(parents=True, exist_ok=True)
            report = folder / "reporte_revision.csv"
            with report.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["N°", "Archivo", "Motivo"])
                for number, item in pending:
                    reasons = []
                    if not item.face_found:
                        reasons.append("rostro no detectado")
                    if self.align_eyes_var.get() and item.face_found and item.eye_line is None:
                        reasons.append("ojos no detectados")
                    left, top, right, bottom = item.crop
                    if left <= 1 or top <= 1 or right >= item.image.width - 1 or bottom >= item.image.height - 1:
                        reasons.append("recorte toca el borde")
                    writer.writerow([number, item.path.name, "; ".join(reasons)])
        except OSError as error:
            messagebox.showerror("No se pudo crear el reporte", str(error))
            return
        self.status_var.set(f"Reporte de revisión creado: {report.name}")
        messagebox.showinfo("Reporte creado", f"Se guardó en:\n{report}")

    @staticmethod
    def available_path(destination: Path) -> Path:
        if not destination.exists():
            return destination
        counter = 2
        while True:
            candidate = destination.with_name(f"{destination.stem}_{counter}{destination.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def export_photos(self, export_all: bool) -> None:
        if not self.photos:
            messagebox.showinfo("Sin fotos", "No hay fotos para exportar.")
            return
        if not self.output_dir_var.get().strip():
            self.choose_output_dir()
            if not self.output_dir_var.get().strip():
                return
        try:
            output_dir = Path(self.output_dir_var.get()).expanduser()
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            messagebox.showerror("Carpeta no disponible", str(error))
            return
        template = self.name_template_var.get().strip() or "{nombre}{sufijo}"
        try:
            template.format(nombre="foto", sufijo="", fecha="2026-01-01")
        except (KeyError, ValueError) as error:
            messagebox.showerror("Plantilla inválida", f"Campo no disponible: {error}. Usá {{nombre}}, {{sufijo}} o {{fecha}}.")
            return
        items = self.photos if export_all else ([self.get_current()] if self.get_current() else [])
        extension, pil_format = EXPORT_FORMATS[self.format_var.get()]
        suffix = self.suffix_var.get().strip()
        saved = 0
        for number, item in enumerate(items, start=1):
            size = self.get_output_size(item.crop)
            if (self.width_var.get().strip() or self.height_var.get().strip()) and size is None:
                return
            name = template.format(nombre=item.path.stem, sufijo=suffix, fecha=date.today().isoformat())
            name = re.sub(r'[<>:"/\\|?*]+', "_", name).strip(". ") or item.path.stem
            image = self.adjusted_image(item).crop(tuple(round(value) for value in item.crop))
            if size:
                image = image.resize(size, Image.Resampling.LANCZOS)
            destination = self.available_path(output_dir / f"{name}{extension}")
            try:
                if pil_format == "JPEG":
                    if image.mode in ("RGBA", "LA"):
                        background = Image.new("RGB", image.size, "white")
                        background.paste(image, mask=image.getchannel("A"))
                        image = background
                    image.convert("RGB").save(destination, pil_format, quality=JPEG_QUALITY, optimize=True)
                elif pil_format == "WEBP":
                    image.save(destination, pil_format, quality=95, method=6)
                elif pil_format == "PNG":
                    image.save(destination, pil_format, optimize=True)
                else:
                    image.save(destination, pil_format)
            except OSError as error:
                messagebox.showerror("Error al exportar", f"No se pudo guardar {item.path.name}: {error}")
                return
            saved += 1
            self.status_var.set(f"Exportando {number} de {len(items)}…")
            self.root.update_idletasks()
        self.status_var.set(f"Listo: se exportaron {saved} foto(s) en {output_dir}.")
        messagebox.showinfo("Exportación terminada", f"Se exportaron {saved} foto(s).")


if __name__ == "__main__":
    RecortadorModerno().run()
