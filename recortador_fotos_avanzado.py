"""Laboratorio de funciones avanzadas para el recortador de fotos."""

from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk
import cv2
import fitz
import numpy as np
import qrcode
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

from recortador_fotos import EXPORT_FORMATS, PhotoItem, SUPPORTED_EXTENSIONS
from recortador_fotos_moderno import RecortadorModerno


class RecortadorAvanzado(RecortadorModerno):
    DEFAULT_CARD_TEMPLATE = {
        "width": 1016, "height": 638, "background": "#ffffff", "background_image": "", "background_mode": "Cubrir",
        "header_enabled": True, "header_height": 94, "header_color": "#0c5e91", "title": "CREDENCIAL", "title_x": 38, "title_y": 30,
        "title_size": 26, "title_color": "#ffffff", "title_font": "Arial", "photo_x": 44, "photo_y": 140, "photo_w": 330, "photo_h": 430,
        "name_x": 430, "name_y": 215, "name_size": 28, "role_x": 430, "role_y": 270,
        "name_color": "#18374e", "name_font": "Arial", "role_size": 20, "role_color": "#567083", "role_font": "Arial",
        "id_x": 430, "id_y": 495, "id_size": 16, "id_color": "#567083", "id_font": "Arial",
        "name_max_w": 520, "role_max_w": 500, "id_max_w": 360,
        "name_align": "Izquierda", "role_align": "Izquierda", "id_align": "Izquierda", "auto_fit_text": True,
        "title_visible": True, "name_visible": True, "role_visible": True, "id_visible": True,
        "logo_path": "", "logo_x": 840, "logo_y": 16, "logo_w": 130, "logo_h": 60,
        "qr_enabled": False, "qr_x": 820, "qr_y": 450, "qr_size": 145, "shapes": [], "custom_texts": [],
    }

    def __init__(self) -> None:
        self.background_mode_var = None
        self.background_strength_var = None
        self.template_var = None
        self.metadata: dict[str, dict[str, str]] = {}
        self.quality_results: dict[str, list[str]] = {}
        self._preview_masks: dict[tuple, np.ndarray] = {}
        self.excel_rows: list[dict] = []
        self.excel_path: Path | None = None
        self.excel_headers: list[str] = []
        self.manual_adjustments: set[str] = set()
        self.last_export_paths: list[Path] = []
        self.redo_history: dict[str, list[dict]] = {}
        self.brand_logo_path: Path | None = None
        self._card_asset_cache: dict[tuple, Image.Image] = {}
        self._card_qr_cache: dict[tuple[str, int], Image.Image] = {}
        super().__init__()
        self.excel_column_var = ctk.StringVar(value="Elegí una planilla primero")
        self.excel_second_column_var = ctk.StringVar(value="Sin segunda columna")
        self.search_var = ctk.StringVar(value="")
        self.brand_name_var = ctk.StringVar(value="CREDENCIAL")
        self.brand_color_var = ctk.StringVar(value="#0c5e91")
        self.card_template = self._load_card_template()
        self.card_template_name_var = ctk.StringVar(value="Credencial estándar")
        self.root.title("Recortador de fotos · laboratorio avanzado")
        self._add_advanced_tab()
        self._add_excel_tab()
        self._add_professional_tab()

    def _add_advanced_tab(self) -> None:
        tab = self.tabs.add("Avanzado")
        tab.grid_columnconfigure(0, weight=1)
        self.background_mode_var = ctk.StringVar(value="Original")
        self.background_strength_var = ctk.DoubleVar(value=55)
        self.template_var = ctk.StringVar(value="Foto sola")
        ctk.CTkLabel(tab, text="Fondo natural", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        ctk.CTkLabel(tab, text="Usa una máscara con bordes difuminados: no genera un corte duro alrededor del pelo.", wraplength=300, justify="left", text_color=self.MUTED).grid(row=1, column=0, sticky="w", padx=10)
        ctk.CTkOptionMenu(tab, values=["Original", "Suavizar fondo", "Fondo claro suave"], variable=self.background_mode_var, command=lambda _value: self.refresh_preview()).grid(row=2, column=0, sticky="ew", padx=10, pady=(8, 3))
        ctk.CTkSlider(tab, from_=20, to=90, variable=self.background_strength_var, progress_color="#16856f", button_color="#16856f", command=lambda _value: self.refresh_preview()).grid(row=3, column=0, sticky="ew", padx=10)
        ctk.CTkLabel(tab, text="La suavidad se aplica al exportar; la foto original nunca se modifica.", text_color=self.MUTED, font=ctk.CTkFont(size=11)).grid(row=4, column=0, sticky="w", padx=10, pady=(0, 10))
        ctk.CTkFrame(tab, height=2, fg_color=("#dce5ec", "#3b4148")).grid(row=5, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(tab, text="Control de calidad", font=ctk.CTkFont(size=16, weight="bold")).grid(row=6, column=0, sticky="w", padx=10, pady=(8, 2))
        ctk.CTkButton(tab, text="Analizar lote: foco, luz, rostro y duplicados", command=self.analyze_batch, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=7, column=0, sticky="ew", padx=10, pady=(5, 6))
        self.quality_box = ctk.CTkTextbox(tab, height=150, wrap="word", fg_color=("#f5f8fa", "#24282d"), text_color=self.TEXT)
        self.quality_box.grid(row=8, column=0, sticky="ew", padx=10)
        self.quality_box.insert("1.0", "Todavía no se analizó el lote.")
        self.quality_box.configure(state="disabled")
        ctk.CTkFrame(tab, height=2, fg_color=("#dce5ec", "#3b4148")).grid(row=9, column=0, sticky="ew", padx=10, pady=12)
        ctk.CTkLabel(tab, text="Tarjeta y datos", font=ctk.CTkFont(size=16, weight="bold")).grid(row=10, column=0, sticky="w", padx=10)
        ctk.CTkOptionMenu(tab, values=["Foto sola", "Tarjeta simple"], variable=self.template_var).grid(row=11, column=0, sticky="ew", padx=10, pady=(5, 4))
        ctk.CTkButton(tab, text="Importar CSV (archivo, nombre, cargo)", command=self.import_csv, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=12, column=0, sticky="ew", padx=10)
        ctk.CTkLabel(tab, text="CSV: columna archivo (con o sin extensión), nombre y cargo. La tarjeta se genera al exportar.", wraplength=300, justify="left", text_color=self.MUTED, font=ctk.CTkFont(size=11)).grid(row=13, column=0, sticky="w", padx=10, pady=(4, 10))

    def _add_excel_tab(self) -> None:
        """Pestaña exclusiva para que la conciliación con Excel siempre sea visible."""
        tab = self.tabs.add("Excel")
        tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(tab, text="Comparar fotos con Excel", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(14, 3))
        ctk.CTkLabel(tab, text="Vinculá cada fila de tu planilla con una foto cargada y generá una copia del Excel con las rutas encontradas.", wraplength=300, justify="left", text_color=self.MUTED).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))
        ctk.CTkButton(tab, text="Seleccionar planilla Excel", command=self.load_excel, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkLabel(tab, text="Primera columna (nombre)", text_color=self.MUTED, font=ctk.CTkFont(size=12)).grid(row=3, column=0, sticky="w", padx=12)
        self.excel_column_menu = ctk.CTkOptionMenu(tab, values=[self.excel_column_var.get()], variable=self.excel_column_var)
        self.excel_column_menu.grid(row=4, column=0, sticky="ew", padx=12, pady=(2, 8))
        ctk.CTkLabel(tab, text="Segunda columna (apellido, opcional)", text_color=self.MUTED, font=ctk.CTkFont(size=12)).grid(row=5, column=0, sticky="w", padx=12)
        self.excel_second_column_menu = ctk.CTkOptionMenu(tab, values=[self.excel_second_column_var.get()], variable=self.excel_second_column_var)
        self.excel_second_column_menu.grid(row=6, column=0, sticky="ew", padx=12, pady=(2, 4))
        ctk.CTkLabel(tab, text="Se aceptan tildes, mayúsculas, espacios, guiones y orden Apellido + Nombre.", wraplength=300, justify="left", text_color=self.MUTED, font=ctk.CTkFont(size=11)).grid(row=7, column=0, sticky="w", padx=12, pady=(0, 12))
        ctk.CTkButton(tab, text="Comparar y crear reporte CSV", command=self.compare_excel, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=8, column=0, sticky="ew", padx=12, pady=(0, 5))
        ctk.CTkButton(tab, text="Crear Excel con rutas de fotos", command=self.create_excel_with_paths, fg_color=("#11806a", "#218c78"), hover_color=("#0c6655", "#176c5c"), font=ctk.CTkFont(weight="bold")).grid(row=9, column=0, sticky="ew", padx=12)
        self.excel_result = ctk.CTkLabel(tab, text="Seleccioná la planilla para comenzar.", wraplength=300, justify="left", text_color=self.MUTED, font=ctk.CTkFont(size=12))
        self.excel_result.grid(row=10, column=0, sticky="w", padx=12, pady=(12, 0))

    def _add_professional_tab(self) -> None:
        """Herramientas de producción agrupadas para no sobrecargar las otras pestañas."""
        tab = self.tabs.add("Profesional")
        panel = ctk.CTkScrollableFrame(tab, fg_color=("#f6f8fa", "#2b2f35"), corner_radius=0)
        panel.pack(fill="both", expand=True, padx=2, pady=2)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(panel, text="Herramientas profesionales", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 2))
        ctk.CTkLabel(panel, text="Revisión, control del lote y trazabilidad antes de imprimir o entregar.", wraplength=300, justify="left", text_color=self.MUTED).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))

        ctk.CTkLabel(panel, text="Buscar en las fotos cargadas", font=ctk.CTkFont(size=14, weight="bold")).grid(row=2, column=0, sticky="w", padx=12)
        search_row = ctk.CTkFrame(panel, fg_color="transparent")
        search_row.grid(row=3, column=0, sticky="ew", padx=12, pady=(3, 10))
        search_row.grid_columnconfigure(0, weight=1)
        entry = ctk.CTkEntry(search_row, textvariable=self.search_var, placeholder_text="Nombre o parte del archivo")
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        entry.bind("<Return>", lambda _event: self.apply_search_filter())
        ctk.CTkButton(search_row, text="Filtrar", width=74, command=self.apply_search_filter, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=0, column=1)
        ctk.CTkButton(panel, text="Ver sólo excepciones", command=self.show_exceptions, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))
        ctk.CTkButton(panel, text="Limpiar filtros", command=self.clear_filters, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 12))

        ctk.CTkFrame(panel, height=2, fg_color=("#dce5ec", "#3b4148")).grid(row=6, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkLabel(panel, text="Control y revisión", font=ctk.CTkFont(size=14, weight="bold")).grid(row=7, column=0, sticky="w", padx=12, pady=(9, 3))
        ctk.CTkButton(panel, text="Analizar lote y actualizar excepciones", command=self.analyze_batch, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=8, column=0, sticky="ew", padx=12, pady=(0, 4))
        ctk.CTkButton(panel, text="Generar hoja PDF de revisión", command=self.export_contact_sheet_pdf, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=9, column=0, sticky="ew", padx=12, pady=(0, 4))
        ctk.CTkButton(panel, text="Validar antes de exportar", command=self.show_export_validation, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=10, column=0, sticky="ew", padx=12, pady=(0, 12))
        ctk.CTkButton(panel, text="Rehacer última acción de esta foto", command=self.redo_current, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=11, column=0, sticky="ew", padx=12, pady=(0, 12))

        ctk.CTkFrame(panel, height=2, fg_color=("#dce5ec", "#3b4148")).grid(row=12, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkLabel(panel, text="Automatización y tarjeta", font=ctk.CTkFont(size=14, weight="bold")).grid(row=13, column=0, sticky="w", padx=12, pady=(9, 3))
        ctk.CTkButton(panel, text="Auto luz sólo en fotos oscuras", command=self.auto_light_dark_only, fg_color=("#11806a", "#218c78"), hover_color=("#0c6655", "#176c5c")).grid(row=14, column=0, sticky="ew", padx=12, pady=(0, 7))
        ctk.CTkLabel(panel, text="Título para tarjeta", text_color=self.MUTED, font=ctk.CTkFont(size=11)).grid(row=15, column=0, sticky="w", padx=12)
        ctk.CTkEntry(panel, textvariable=self.brand_name_var).grid(row=16, column=0, sticky="ew", padx=12, pady=(2, 6))
        ctk.CTkLabel(panel, text="Color institucional (hexadecimal)", text_color=self.MUTED, font=ctk.CTkFont(size=11)).grid(row=17, column=0, sticky="w", padx=12)
        ctk.CTkEntry(panel, textvariable=self.brand_color_var, placeholder_text="#0c5e91").grid(row=18, column=0, sticky="ew", padx=12, pady=(2, 6))
        ctk.CTkButton(panel, text="Elegir logo opcional", command=self.choose_brand_logo, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=19, column=0, sticky="ew", padx=12, pady=(0, 12))
        ctk.CTkButton(panel, text="Diseñar credencial", command=self.open_card_designer, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER, font=ctk.CTkFont(weight="bold")).grid(row=20, column=0, sticky="ew", padx=12, pady=(0, 12))

        ctk.CTkFrame(panel, height=2, fg_color=("#dce5ec", "#3b4148")).grid(row=21, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkLabel(panel, text="Privacidad", font=ctk.CTkFont(size=14, weight="bold")).grid(row=22, column=0, sticky="w", padx=12, pady=(9, 3))
        ctk.CTkLabel(panel, text="Elimina de memoria los datos CSV/Excel, las rutas y la carpeta recordada. No borra fotos ni planillas originales.", wraplength=300, justify="left", text_color=self.MUTED, font=ctk.CTkFont(size=11)).grid(row=23, column=0, sticky="w", padx=12, pady=(0, 5))
        ctk.CTkButton(panel, text="Limpiar datos locales de esta sesión", command=self.clear_sensitive_data, fg_color=self.DANGER, text_color=self.DANGER_TEXT, hover_color=self.DANGER_HOVER).grid(row=24, column=0, sticky="ew", padx=12, pady=(0, 14))

    def apply_search_filter(self) -> None:
        self.rebuild_list()
        self.status_var.set("Filtro aplicado." if self.search_var.get().strip() else "Filtro de nombre quitado.")

    def show_exceptions(self) -> None:
        self.filter_review_var.set(True)
        self.rebuild_list()
        self.status_var.set("Mostrando sólo fotos que requieren revisión.")

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.filter_review_var.set(False)
        self.rebuild_list()
        self.status_var.set("Se muestran todas las fotos.")

    @staticmethod
    def _hash(image: Image.Image) -> np.ndarray:
        gray = np.asarray(image.convert("L").resize((16, 16), Image.Resampling.LANCZOS))
        return gray > gray.mean()

    def add_photos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Seleccionar fotos o PDF", initialdir=self.last_input_dir or None,
            filetypes=[("Fotos y PDF", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.pdf"), ("Todos", "*.*")],
        )
        if not paths:
            return
        self.last_input_dir = str(Path(paths[0]).parent)
        self._save_session()
        image_paths = [Path(path) for path in paths if Path(path).suffix.lower() in SUPPORTED_EXTENSIONS]
        pdf_paths = [Path(path) for path in paths if Path(path).suffix.lower() == ".pdf"]
        if image_paths:
            self._add_paths(image_paths)
        for path in pdf_paths:
            self._add_pdf(path)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Seleccionar carpeta con fotos o PDF", initialdir=self.last_input_dir or None)
        if not folder:
            return
        self.last_input_dir = folder
        self._save_session()
        files = [path for path in Path(folder).iterdir() if path.is_file()]
        self._add_paths(path for path in files if path.suffix.lower() in SUPPORTED_EXTENSIONS)
        for path in files:
            if path.suffix.lower() == ".pdf":
                self._add_pdf(path)

    def _add_pdf(self, path: Path) -> None:
        added = 0
        try:
            document = fitz.open(path)
            if document.page_count > 40:
                if not messagebox.askyesno("PDF extenso", f"{path.name} tiene {document.page_count} páginas. ¿Cargar todas?"):
                    document.close()
                    return
            for number, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                virtual_path = path.with_name(f"{path.stem}_p{number:02d}.png")
                self.photos.append(PhotoItem(virtual_path, image, self.default_crop(*image.size)))
                added += 1
            document.close()
        except (fitz.FileDataError, RuntimeError, OSError) as error:
            messagebox.showerror("PDF no cargado", f"No se pudo leer {path.name}: {error}")
            return
        if added:
            self.rebuild_list()
            if self.current_index is None:
                self.select_photo(0)
            self.status_var.set(f"Se cargaron {added} página(s) de {path.name} a 300 DPI.")

    def analyze_batch(self) -> None:
        if not self.photos:
            messagebox.showinfo("Sin fotos", "Primero agregá fotos al lote.")
            return
        self.quality_results = {}
        hashes = []
        for item in self.photos:
            gray = np.asarray(item.image.convert("L"))
            reasons = []
            blur = cv2.Laplacian(gray, cv2.CV_64F).var()
            if blur < 45:
                reasons.append("posible desenfoque")
            brightness, contrast = float(gray.mean()), float(gray.std())
            if brightness < 62:
                reasons.append("muy oscura")
            elif brightness > 205:
                reasons.append("muy clara")
            if contrast < 22:
                reasons.append("contraste bajo")
            face = item.face_box or self.find_largest_face(item.image)
            if face is None:
                reasons.append("rostro no detectado")
            elif face[3] < item.image.height * 0.12:
                reasons.append("rostro pequeño")
            if self.align_eyes_var.get() and item.eye_line is None:
                reasons.append("ojos sin confirmar")
            hashes.append((item, self._hash(item.image)))
            self.quality_results[str(item.path)] = reasons
        for index, (item, current_hash) in enumerate(hashes):
            for other, other_hash in hashes[index + 1:]:
                if np.count_nonzero(current_hash != other_hash) < 10:
                    self.quality_results[str(item.path)].append(f"posible duplicado de {other.path.name}")
                    self.quality_results[str(other.path)].append(f"posible duplicado de {item.path.name}")
        lines = []
        for item in self.photos:
            issues = self.quality_results[str(item.path)]
            lines.append(f"{'⚠' if issues else '✓'} {item.path.name}: {', '.join(issues) if issues else 'aprobada'}")
        self.quality_box.configure(state="normal")
        self.quality_box.delete("1.0", "end")
        self.quality_box.insert("1.0", "\n".join(lines))
        self.quality_box.configure(state="disabled")
        self.rebuild_list()
        self.status_var.set("Control de calidad terminado.")

    def needs_review(self, item) -> bool:
        return super().needs_review(item) or bool(self.quality_results.get(str(item.path)))

    def photo_status(self, item) -> str:
        issues = self.quality_results.get(str(item.path), [])
        if issues:
            return "Revisar: " + ", ".join(issues[:2])
        if super().needs_review(item):
            return "Revisar encuadre o detección"
        if str(item.path) in self.manual_adjustments:
            return "Ajustado manualmente"
        return "Listo"

    def rebuild_list(self) -> None:
        """Lista rápida con filtro de revisión y búsqueda por nombre de archivo."""
        if not hasattr(self, "photo_list_container"):
            return
        for widget in self.photo_list_container.winfo_children():
            widget.destroy()
        query = getattr(self, "search_var", None)
        query_text = query.get().casefold().strip() if query is not None else ""
        self.visible_indices = [
            index for index, item in enumerate(self.photos)
            if (not self.filter_review_var.get() or self.needs_review(item))
            and (not query_text or query_text in item.path.name.casefold())
        ]
        pending = sum(self.needs_review(item) for item in self.photos)
        self.review_count_label.configure(text=f"{len(self.photos) - pending} listas · {pending} para revisar")
        self._photo_buttons = {}
        for index in self.visible_indices:
            item = self.photos[index]
            review = self.needs_review(item)
            selected = index == self.current_index
            prefix = "⚠" if review else ("✎" if str(item.path) in self.manual_adjustments else "✓")
            button = ctk.CTkButton(
                self.photo_list_container, anchor="w", text=f"{prefix}  {item.path.name}", height=38,
                fg_color="#1b78b4" if selected else ("#fff4e6" if review else "transparent"),
                text_color="white" if selected else ("#9a5413" if review else ("#31485b", "#e5ebf0")),
                hover_color="#dbeaf4" if not selected else "#15669b",
                command=lambda chosen=index: self.select_photo(chosen),
            )
            button.pack(fill="x", padx=2, pady=2)
            self._photo_buttons[index] = button

    def _mark_current_manual(self) -> None:
        item = self.get_current()
        if item is not None:
            self.manual_adjustments.add(str(item.path))

    def end_drag(self, event) -> None:
        was_dragging = self._drag_start is not None
        super().end_drag(event)
        if was_dragging:
            self._mark_current_manual()
            self.rebuild_list()

    def zoom_current(self, factor: float) -> None:
        super().zoom_current(factor)
        self._mark_current_manual()

    def rotate_current(self, degrees: int) -> None:
        super().rotate_current(degrees)
        self._mark_current_manual()

    def change_brightness(self, value: str) -> None:
        super().change_brightness(value)
        self._mark_current_manual()

    def change_contrast(self, value: str) -> None:
        super().change_contrast(value)
        self._mark_current_manual()

    def change_hair_margin(self, value: str) -> None:
        super().change_hair_margin(value)
        self._mark_current_manual()

    @staticmethod
    def _item_state(item: PhotoItem) -> dict:
        return {"image": item.image.copy(), "crop": item.crop, "face_found": item.face_found, "face_box": item.face_box, "eye_line": item.eye_line, "eyes_checked": item.eyes_checked, "hair_margin": item.hair_margin, "brightness": item.brightness, "contrast": item.contrast}

    def snapshot_item(self, item: PhotoItem) -> None:
        super().snapshot_item(item)
        self.redo_history.pop(str(item.path), None)

    def undo_current(self) -> None:
        item = self.get_current()
        history = self.history.get(str(item.path)) if item else None
        if not item or not history:
            self.status_var.set("No hay acciones para deshacer en esta foto.")
            return
        self.redo_history.setdefault(str(item.path), []).append(self._item_state(item))
        state = history.pop()
        for key, value in state.items():
            setattr(item, key, value)
        self.sync_adjustment_controls()
        self.rebuild_list()
        self.refresh_preview()
        self.status_var.set("Se deshizo la última acción de esta foto.")

    def redo_current(self) -> None:
        item = self.get_current()
        history = self.redo_history.get(str(item.path)) if item else None
        if not item or not history:
            self.status_var.set("No hay acciones para rehacer en esta foto.")
            return
        self.history.setdefault(str(item.path), []).append(self._item_state(item))
        state = history.pop()
        for key, value in state.items():
            setattr(item, key, value)
        self.sync_adjustment_controls()
        self.rebuild_list()
        self.refresh_preview()
        self.status_var.set("Se rehizo la última acción de esta foto.")

    def import_csv(self) -> None:
        path = filedialog.askopenfilename(title="Importar datos", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as file:
                for row in csv.DictReader(file):
                    key = Path(row.get("archivo", "")).stem.lower()
                    if key:
                        self.metadata[key] = {str(k).lower(): str(v) for k, v in row.items()}
        except (OSError, csv.Error) as error:
            messagebox.showerror("CSV inválido", str(error))
            return
        self.status_var.set(f"Se importaron datos para {len(self.metadata)} archivo(s).")

    def load_excel(self) -> None:
        path = filedialog.askopenfilename(title="Seleccionar listado Excel", filetypes=[("Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")])
        if not path:
            return
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
            sheet = workbook.active
            rows = sheet.iter_rows(values_only=True)
            headers = [str(value).strip() if value is not None else "" for value in next(rows)]
            headers = [header if header else f"Columna {index + 1}" for index, header in enumerate(headers)]
            self.excel_rows = []
            self.excel_headers = headers
            for row_number, row in enumerate(rows, start=2):
                values = {headers[index]: "" if value is None else str(value).strip() for index, value in enumerate(row[:len(headers)])}
                values["__row__"] = str(row_number)
                self.excel_rows.append(values)
            workbook.close()
        except (OSError, StopIteration, ValueError) as error:
            messagebox.showerror("Planilla no válida", f"No se pudo leer el Excel: {error}")
            return
        self.excel_path = Path(path)
        self.excel_column_menu.configure(values=headers)
        self.excel_second_column_menu.configure(values=["Sin segunda columna", *headers])
        self.excel_column_var.set(headers[0])
        self.excel_second_column_var.set("Sin segunda columna")
        self.excel_result.configure(text=f"Planilla cargada: {len(self.excel_rows)} fila(s). Elegí la columna con los nombres o archivos.")

    @staticmethod
    def _name_keys(value: str) -> set[str]:
        tokens = RecortadorAvanzado._name_tokens(value)
        if not tokens:
            return set()
        return {"".join(tokens), "".join(sorted(tokens))}

    @staticmethod
    def _name_tokens(value: str) -> set[str]:
        """Normaliza cada componente del nombre para una coincidencia tolerante."""
        text = Path(str(value).strip()).stem
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").casefold()
        text = re.sub(r"(?:[_ -](?:p|pagina|page)\d+|_recortada)$", "", text)
        return set(re.findall(r"[a-z0-9]+", text))

    def compare_excel(self) -> None:
        column = self.excel_column_var.get()
        if not self.excel_rows or not column or column == "Elegí una planilla primero":
            messagebox.showinfo("Planilla requerida", "Primero seleccioná un Excel y la columna a comparar.")
            return
        second_column = self.excel_second_column_var.get()
        expected: set[str] = set()
        for row in self.excel_rows:
            first = row.get(column, "").strip()
            second = "" if second_column == "Sin segunda columna" else row.get(second_column, "").strip()
            value = " ".join(part for part in (first, second) if part)
            if value and self._name_keys(value):
                expected.add(value)
        missing = []
        matched_paths: set[Path] = set()
        for value in expected:
            matches = self._matches_for_value(value)
            if matches:
                matched_paths.update(matches)
            else:
                missing.append(value)
        extras = sorted(item.path.name for item in self.photos if item.path not in matched_paths)
        missing.sort()
        report_folder = Path(self.output_dir_var.get()) if self.output_dir_var.get().strip() else self.preset_path.parent
        report = report_folder / "comparacion_excel_fotos.csv"
        try:
            report_folder.mkdir(parents=True, exist_ok=True)
            with report.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["Estado", "Nombre o archivo"])
                writer.writerows(("Falta foto", value) for value in missing)
                writer.writerows(("Foto sin registro", value) for value in extras)
        except OSError as error:
            messagebox.showerror("No se pudo crear el reporte", str(error))
            return
        self.excel_result.configure(text=f"Resultado: {len(missing)} sin foto · {len(extras)} fotos sin registro. Reporte: {report.name}")
        self.status_var.set("Comparación con Excel terminada.")

    def _matches_for_value(self, value: str) -> list[Path]:
        keys = self._name_keys(value)
        expected_tokens = self._name_tokens(value)
        exact_matches = []
        extended_matches = []
        for item in self.photos:
            if keys.intersection(self._name_keys(item.path.stem)):
                exact_matches.append(item.path)
            elif len(expected_tokens) >= 2 and expected_tokens.issubset(self._name_tokens(item.path.stem)):
                # Ej.: Excel "Bell Enriquez" y archivo "Bell Mary Enriquez.jpg".
                extended_matches.append(item.path)
        return exact_matches or extended_matches

    def _match_status(self, value: str, path: Path) -> str:
        if self._name_keys(value).intersection(self._name_keys(path.stem)):
            return "Coincidencia"
        return "Coincidencia ampliada (nombre adicional)"

    def create_excel_with_paths(self) -> None:
        column = self.excel_column_var.get()
        if not self.excel_path or not self.excel_rows or column == "Elegí una planilla primero":
            messagebox.showinfo("Planilla requerida", "Primero seleccioná el Excel y las columnas a comparar.")
            return
        second_column = self.excel_second_column_var.get()
        try:
            workbook = load_workbook(self.excel_path)
            sheet = workbook.active
            route_column = sheet.max_column + 1
            sheet.cell(1, route_column, "Ruta de foto coincidente")
            sheet.cell(1, route_column + 1, "Archivo coincidente")
            sheet.cell(1, route_column + 2, "Estado de coincidencia")
            found = ambiguous = 0
            for row in self.excel_rows:
                first = row.get(column, "").strip()
                second = "" if second_column == "Sin segunda columna" else row.get(second_column, "").strip()
                value = " ".join(part for part in (first, second) if part)
                matches = self._matches_for_value(value) if value else []
                row_number = int(row["__row__"])
                if len(matches) == 1:
                    sheet.cell(row_number, route_column, str(matches[0]))
                    sheet.cell(row_number, route_column + 1, matches[0].name)
                    sheet.cell(row_number, route_column + 2, self._match_status(value, matches[0]))
                    found += 1
                elif len(matches) > 1:
                    sheet.cell(row_number, route_column, " | ".join(str(path) for path in matches))
                    sheet.cell(row_number, route_column + 1, " | ".join(path.name for path in matches))
                    sheet.cell(row_number, route_column + 2, "Revisar: más de una coincidencia")
                    ambiguous += 1
                else:
                    sheet.cell(row_number, route_column + 2, "Sin foto coincidente")
            for offset in range(3):
                sheet.column_dimensions[get_column_letter(route_column + offset)].width = 48 if offset == 0 else 30
            destination = self.excel_path.with_name(f"{self.excel_path.stem}_con_rutas.xlsx")
            workbook.save(destination)
            workbook.close()
        except OSError as error:
            messagebox.showerror("No se pudo crear el Excel", str(error))
            return
        self.excel_result.configure(text=f"Excel creado: {found} ruta(s) agregadas · {ambiguous} coincidencia(s) para revisar.")
        self.status_var.set(f"Planilla con rutas creada: {destination.name}")
        messagebox.showinfo("Excel creado", f"Se guardó una copia en:\n{destination}")

    def _foreground_mask(self, image: Image.Image, face_box) -> np.ndarray:
        """Segmentación conservadora: prioriza una transición suave antes que un borde perfecto."""
        rgb = np.asarray(image.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        height, width = bgr.shape[:2]
        if not face_box:
            return np.ones((height, width), np.float32)
        mask = np.full((height, width), cv2.GC_PR_BGD, np.uint8)
        mask[:5, :] = mask[-5:, :] = cv2.GC_BGD
        mask[:, :5] = mask[:, -5:] = cv2.GC_BGD
        if face_box:
            x, y, w, h = face_box
            x, y = max(0, x), max(0, y)
            mask[y:min(height, y + h), x:min(width, x + w)] = cv2.GC_FGD
            # Zona probable de cuerpo debajo del rostro, sin marcarla como primer plano seguro.
            mask[max(0, y - h):min(height, y + h * 4), max(0, x - w):min(width, x + w * 2)] = cv2.GC_PR_FGD
        bg_model, fg_model = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(bgr, mask, None, bg_model, fg_model, 3, cv2.GC_INIT_WITH_MASK)
        except cv2.error:
            return np.ones((height, width), np.float32)
        foreground = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
        return cv2.GaussianBlur(foreground, (0, 0), 3.0)

    def process_background(self, image: Image.Image, item, face_box=None, mask=None) -> Image.Image:
        mode = self.background_mode_var.get() if self.background_mode_var else "Original"
        if mode == "Original":
            return image
        face = face_box
        mask = (mask if mask is not None else self._foreground_mask(image, face))[..., None]
        strength = (self.background_strength_var.get() if self.background_strength_var else 55) / 100
        rgb = np.asarray(image.convert("RGB")).astype(np.float32)
        blur_radius = max(2, int(8 + strength * 18))
        background = np.asarray(image.convert("RGB").filter(ImageFilter.GaussianBlur(blur_radius))).astype(np.float32)
        if mode == "Fondo claro suave":
            background = background * (1 - strength * 0.75) + np.array([248, 248, 244], dtype=np.float32) * strength * 0.75
        result = rgb * mask + background * (1 - mask)
        return Image.fromarray(np.uint8(np.clip(result, 0, 255)))

    def refresh_preview(self) -> None:
        """Vista previa con fondo en tiempo real, usando una máscara reducida en caché."""
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        item = self.get_current()
        if item is None:
            self.canvas.create_text(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2, text="Agregá fotos para comenzar", fill="#d7e2ec", font=("Segoe UI", 14))
            self.preview_info.configure(text="")
            return
        canvas_w, canvas_h = max(self.canvas.winfo_width(), 1), max(self.canvas.winfo_height(), 1)
        source = item.image if self.show_original else self.adjusted_image(item)
        source_scale = min(1.0, 900 / max(source.size))
        if source_scale < 1:
            working = source.resize((round(source.width * source_scale), round(source.height * source_scale)), Image.Resampling.LANCZOS)
        else:
            working = source.copy()
        if not self.show_original and self.background_mode_var is not None and self.background_mode_var.get() != "Original":
            face = None
            if item.face_box:
                x, y, w, h = item.face_box
                face = (round(x * source_scale), round(y * source_scale), round(w * source_scale), round(h * source_scale))
            cache_key = (str(item.path), id(item.image), working.size, face)
            if cache_key not in self._preview_masks:
                self._preview_masks[cache_key] = self._foreground_mask(working, face)
            working = self.process_background(working, item, face, self._preview_masks[cache_key])
        scale = min((canvas_w - 24) / working.width, (canvas_h - 24) / working.height)
        display_w, display_h = max(1, int(working.width * scale)), max(1, int(working.height * scale))
        origin_x, origin_y = (canvas_w - display_w) // 2, (canvas_h - display_h) // 2
        preview = working.copy()
        preview.thumbnail((display_w, display_h), Image.Resampling.LANCZOS)
        from PIL import ImageTk
        self._preview_photo = ImageTk.PhotoImage(preview)
        self.canvas.create_image(origin_x, origin_y, image=self._preview_photo, anchor="nw")
        self._display_origin = (origin_x, origin_y)
        self._display_scale = preview.width / item.image.width
        left, top, right, bottom = item.crop
        x1, y1 = origin_x + left * self._display_scale, origin_y + top * self._display_scale
        x2, y2 = origin_x + right * self._display_scale, origin_y + bottom * self._display_scale
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#ffffff", width=3)
        self.canvas.create_rectangle(x1 + 3, y1 + 3, x2 - 3, y2 - 3, outline="#37aee2", width=1)
        mode = "Original" if self.show_original else (self.background_mode_var.get() if self.background_mode_var else "Resultado")
        self.preview_info.configure(text=f"{mode} · vista previa rápida · {item.image.width} × {item.image.height} px")

    @property
    def card_template_path(self) -> Path:
        return self.preset_path.with_name("plantilla_credencial.json")

    def _load_card_template(self) -> dict:
        template = json.loads(json.dumps(self.DEFAULT_CARD_TEMPLATE))
        try:
            saved = json.loads(self.card_template_path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                template.update({key: value for key, value in saved.items() if key in template})
        except (OSError, json.JSONDecodeError):
            pass
        return template

    def _save_card_template(self) -> None:
        try:
            self.card_template_path.write_text(json.dumps(self.card_template, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("No se pudo guardar la plantilla", str(error))

    @staticmethod
    def _safe_color(value: str, fallback: str) -> str:
        return value if re.fullmatch(r"#[0-9a-fA-F]{6}", str(value).strip()) else fallback

    @staticmethod
    @lru_cache(maxsize=1)
    def _installed_card_fonts() -> dict[str, tuple[str, str]]:
        """Devuelve las familias de Windows con una ruta normal y otra en negrita."""
        fallback = {
            "Arial": ("arial.ttf", "arialbd.ttf"), "Georgia": ("georgia.ttf", "georgiab.ttf"),
            "Verdana": ("verdana.ttf", "verdanab.ttf"), "Courier New": ("cour.ttf", "courbd.ttf"),
        }
        catalog = dict(fallback)
        if os.name != "nt":
            return catalog
        try:
            import winreg

            fonts_dir = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Fonts"
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
            index = 0
            while True:
                try:
                    display_name, filename, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if not isinstance(filename, str):
                    continue
                path = fonts_dir / filename
                if not path.is_file() or not path.suffix.lower() in {".ttf", ".otf", ".ttc"}:
                    continue
                family = re.sub(r"\s*\(.*?\)\s*", "", display_name).strip()
                family = re.sub(r"\s+(Bold|Italic|Oblique|Regular|Light|Medium|Semibold|Black|Thin)(\s+Italic)?$", "", family, flags=re.I).strip()
                if not family:
                    continue
                normal, bold = catalog.get(family, (str(path), str(path)))
                if re.search(r"bold|black|semibold", display_name, flags=re.I):
                    bold = str(path)
                elif re.search(r"italic|oblique", display_name, flags=re.I):
                    continue
                else:
                    normal = str(path)
                catalog[family] = (normal, bold)
        except OSError:
            pass
        return dict(sorted(catalog.items(), key=lambda item: item[0].casefold()))

    @staticmethod
    @lru_cache(maxsize=512)
    def _card_font(size: int, bold: bool = False, family: str = "Arial"):
        catalog = RecortadorAvanzado._installed_card_fonts()
        normal, bold_name = catalog.get(family, catalog.get("Arial", ("arial.ttf", "arialbd.ttf")))
        try:
            return ImageFont.truetype(bold_name if bold else normal, max(8, int(size)))
        except OSError:
            return ImageFont.load_default()

    def _draw_card_text(self, draw: ImageDraw.ImageDraw, text: str, template: dict, prefix: str, *, bold: bool = False) -> None:
        """Dibuja texto de la tarjeta y reduce su tamaño cuando supera el espacio disponible."""
        size = max(8, int(template.get(f"{prefix}_size", 16)))
        max_width = max(40, int(template.get(f"{prefix}_max_w", 500)))
        family = str(template.get(f"{prefix}_font", "Arial"))
        font = self._card_font(size, bold, family)
        if template.get("auto_fit_text", True):
            while size > 9 and draw.textbbox((0, 0), text, font=font)[2] > max_width:
                size -= 1
                font = self._card_font(size, bold, family)
        text_width = draw.textbbox((0, 0), text, font=font)[2]
        x = int(template.get(f"{prefix}_x", 0))
        align = template.get(f"{prefix}_align", "Izquierda")
        if align == "Centro":
            x += max(0, (max_width - text_width) // 2)
        elif align == "Derecha":
            x += max(0, max_width - text_width)
        draw.text((x, int(template.get(f"{prefix}_y", 0))), text, fill=self._safe_color(template.get(f"{prefix}_color", "#18374e"), "#18374e"), font=font)

    def _card_values(self, item) -> tuple[str, str, str, str]:
        data = self.metadata.get(item.path.stem.lower(), {}) if item else {}
        name = data.get("nombre", item.path.stem if item else "NOMBRE Y APELLIDO")
        role = data.get("cargo", "Cargo / sector")
        identifier = data.get("documento", data.get("doc", data.get("id", item.path.stem if item else "000000")))
        qr_value = data.get("qr", identifier)
        return name, role, identifier, qr_value

    def render_card(self, photo: Image.Image, item=None, template: dict | None = None) -> Image.Image:
        template = dict(self.card_template if template is None else template)
        width, height = max(200, int(template["width"])), max(150, int(template["height"]))
        background = self._safe_color(template.get("background", "#ffffff"), "#ffffff")
        header_color = self._safe_color(template.get("header_color", self.brand_color_var.get()), "#0c5e91")
        card = Image.new("RGB", (width, height), background)
        background_image = Path(str(template.get("background_image", "")))
        if background_image.is_file():
            try:
                asset_key = ("background", str(background_image), background_image.stat().st_mtime_ns, width, height)
                if asset_key not in self._card_asset_cache:
                    with Image.open(background_image) as source:
                        image = source.convert("RGB")
                        scale = max(width / image.width, height / image.height)
                        resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
                        left, top = (resized.width - width) // 2, (resized.height - height) // 2
                        self._card_asset_cache[asset_key] = resized.crop((left, top, left + width, top + height))
                card = self._card_asset_cache[asset_key].copy()
            except OSError:
                pass
        draw = ImageDraw.Draw(card)
        header_height = min(height, max(0, int(template["header_height"])))
        if template.get("header_enabled", True) and header_height:
            draw.rectangle((0, 0, width, header_height), fill=header_color)
        def draw_shape(shape: dict) -> None:
            x, y = int(shape.get("x", 0)), int(shape.get("y", 0))
            shape_w, shape_h = max(1, int(shape.get("w", 100))), max(1, int(shape.get("h", 70)))
            fill = self._safe_color(shape.get("fill", "#dbeafe"), "#dbeafe")
            outline = self._safe_color(shape.get("outline", fill), fill)
            if shape.get("type") == "Círculo":
                draw.ellipse((x, y, x + shape_w, y + shape_h), fill=fill, outline=outline, width=max(1, int(shape.get("stroke", 1))))
            elif shape.get("type") == "Línea":
                draw.line((x, y, x + shape_w, y + shape_h), fill=fill, width=max(1, int(shape.get("stroke", 5))))
            else:
                draw.rectangle((x, y, x + shape_w, y + shape_h), fill=fill, outline=outline, width=max(1, int(shape.get("stroke", 1))))
        shapes = [shape for shape in template.get("shapes", []) if isinstance(shape, dict)]
        for shape in sorted((shape for shape in shapes if int(shape.get("z", 30)) <= 35), key=lambda shape: int(shape.get("z", 30))):
            draw_shape(shape)
        title = str(template.get("title", self.brand_name_var.get())).strip() or "CREDENCIAL"
        if template.get("title_visible", True):
            draw.text((int(template["title_x"]), int(template["title_y"])), title.upper(), fill=self._safe_color(template.get("title_color", "#ffffff"), "#ffffff"), font=self._card_font(template["title_size"], True, template.get("title_font", "Arial")))
        logo_source = Path(str(template.get("logo_path", ""))) if template.get("logo_path") else self.brand_logo_path
        if logo_source:
            try:
                with Image.open(logo_source) as source:
                    logo = source.convert("RGBA")
                logo.thumbnail((max(20, int(template.get("logo_w", 130))), max(20, int(template.get("logo_h", 60)))), Image.Resampling.LANCZOS)
                card.paste(logo, (max(0, int(template.get("logo_x", 0))), max(0, int(template.get("logo_y", 0)))), logo)
            except OSError:
                pass
        photo_x, photo_y = int(template["photo_x"]), int(template["photo_y"])
        photo_w, photo_h = max(20, int(template["photo_w"])), max(20, int(template["photo_h"]))
        frame = Image.new("RGB", (photo_w, photo_h), "#edf1f4")
        portrait = photo.convert("RGB").copy()
        portrait.thumbnail((photo_w, photo_h), Image.Resampling.LANCZOS)
        frame.paste(portrait, ((photo_w - portrait.width) // 2, (photo_h - portrait.height) // 2))
        card.paste(frame, (photo_x, photo_y))
        name, role, identifier, qr_value = self._card_values(item)
        if template.get("name_visible", True):
            self._draw_card_text(draw, name.upper(), template, "name", bold=True)
        if template.get("role_visible", True):
            self._draw_card_text(draw, role, template, "role")
        if template.get("id_visible", True):
            self._draw_card_text(draw, f"ID: {identifier}", template, "id")
        if template.get("qr_enabled"):
            qr_size = max(30, int(template["qr_size"]))
            qr_key = (str(qr_value), qr_size)
            if qr_key not in self._card_qr_cache:
                self._card_qr_cache[qr_key] = qrcode.make(qr_value).convert("RGB").resize((qr_size, qr_size), Image.Resampling.NEAREST)
            qr = self._card_qr_cache[qr_key]
            card.paste(qr, (int(template["qr_x"]), int(template["qr_y"])))
        replacements = {"{nombre}": name, "{cargo}": role, "{id}": identifier}
        for custom in sorted((entry for entry in template.get("custom_texts", []) if isinstance(entry, dict)), key=lambda entry: int(entry.get("z", 60))):
            if not custom.get("visible", True):
                continue
            custom_text = str(custom.get("text", ""))
            for token, replacement in replacements.items():
                custom_text = custom_text.replace(token, replacement)
            size = max(8, int(custom.get("size", 20)))
            maximum = max(40, int(custom.get("max_w", 360)))
            family = str(custom.get("font", "Arial"))
            font = self._card_font(size, bool(custom.get("bold", False)), family)
            if template.get("auto_fit_text", True):
                while size > 9 and draw.textbbox((0, 0), custom_text, font=font)[2] > maximum:
                    size -= 1
                    font = self._card_font(size, bool(custom.get("bold", False)), family)
            text_width = draw.textbbox((0, 0), custom_text, font=font)[2]
            x = int(custom.get("x", 0))
            if custom.get("align") == "Centro":
                x += max(0, (maximum - text_width) // 2)
            elif custom.get("align") == "Derecha":
                x += max(0, maximum - text_width)
            draw.text((x, int(custom.get("y", 0))), custom_text, fill=self._safe_color(custom.get("color", "#18374e"), "#18374e"), font=font)
        for shape in sorted((shape for shape in shapes if int(shape.get("z", 30)) > 35), key=lambda shape: int(shape.get("z", 30))):
            draw_shape(shape)
        return card

    def make_card(self, photo: Image.Image, item) -> Image.Image:
        return self.render_card(photo, item)

    def _designer_sample_photo(self) -> tuple[Image.Image, object | None]:
        item = self.get_current()
        if item is not None:
            return self.adjusted_image(item).crop(tuple(round(value) for value in item.crop)), item
        sample = Image.new("RGB", (330, 430), "#e7edf1")
        ImageDraw.Draw(sample).text((78, 205), "FOTO", fill="#718096", font=self._card_font(22, True))
        return sample, None

    def _card_export_photo(self, item) -> Image.Image:
        left, _top, _right, _bottom = item.crop
        photo = self.adjusted_image(item).crop(tuple(round(value) for value in item.crop))
        face_box = None
        if item.face_box:
            x, y, width, height = item.face_box
            face_box = (int(x - left), int(y - item.crop[1]), width, height)
        return self.process_background(photo, item, face_box)

    def export_designer_cards(self, template: dict, export_all: bool, format_name: str, output_dir: Path) -> tuple[bool, str]:
        items = self.photos if export_all else ([self.get_current()] if self.get_current() else [])
        if not items:
            return False, "No hay una foto seleccionada para exportar."
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            cards = [(item, self.render_card(self._card_export_photo(item), item, template)) for item in items]
            if format_name == "PDF":
                destination = self.available_path(output_dir / ("credenciales.pdf" if export_all else f"{Path(items[0].path).stem}.pdf"))
                cards[0][1].convert("RGB").save(destination, "PDF", resolution=150.0, save_all=True, append_images=[card.convert("RGB") for _item, card in cards[1:]])
                return True, f"PDF creado: {destination.name} ({len(cards)} credencial(es))."
            extension, pil_format = EXPORT_FORMATS[format_name]
            for item, card in cards:
                destination = self.available_path(output_dir / f"{Path(item.path).stem}{extension}")
                if pil_format == "JPEG":
                    card.convert("RGB").save(destination, pil_format, quality=95, optimize=True)
                elif pil_format == "WEBP":
                    card.save(destination, pil_format, quality=95, method=6)
                else:
                    card.save(destination, pil_format, optimize=True)
            return True, f"Se exportaron {len(cards)} credencial(es) como {format_name}."
        except OSError as error:
            return False, f"No se pudieron exportar las credenciales: {error}"

    def open_card_designer(self) -> None:
        window = ctk.CTkToplevel(self.root)
        window.title("Diseñar credencial")
        window.geometry("1240x780")
        window.minsize(1020, 650)
        window.transient(self.root)
        state = json.loads(json.dumps(self.card_template))
        state["title"] = state.get("title") or self.brand_name_var.get()
        state["header_color"] = state.get("header_color") or self.brand_color_var.get()
        variables = {key: tk.StringVar(value=str(value)) for key, value in state.items() if key not in ("qr_enabled", "header_enabled", "auto_fit_text", "title_visible", "name_visible", "role_visible", "id_visible", "shapes", "custom_texts")}
        qr_var = tk.BooleanVar(value=bool(state.get("qr_enabled")))
        header_var = tk.BooleanVar(value=bool(state.get("header_enabled", True)))
        title_visible_var = tk.BooleanVar(value=bool(state.get("title_visible", True)))
        name_visible_var = tk.BooleanVar(value=bool(state.get("name_visible", True)))
        role_visible_var = tk.BooleanVar(value=bool(state.get("role_visible", True)))
        id_visible_var = tk.BooleanVar(value=bool(state.get("id_visible", True)))
        shapes: list[dict] = [dict(shape) for shape in state.get("shapes", []) if isinstance(shape, dict)]
        custom_texts: list[dict] = [dict(entry) for entry in state.get("custom_texts", []) if isinstance(entry, dict)]
        selected = tk.StringVar(value="Foto")
        canvas = tk.Canvas(window, background="#182433", highlightthickness=0, cursor="fleur")
        canvas.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=14)
        controls = ctk.CTkScrollableFrame(window, width=330, fg_color=("#f5f8fa", "#252a30"))
        controls.grid(row=0, column=1, sticky="nsew", padx=(8, 14), pady=14)
        window.grid_columnconfigure(0, weight=1)
        window.grid_columnconfigure(1, minsize=345)
        window.grid_rowconfigure(0, weight=1)
        preview_ref: dict[str, object] = {}
        drag = {"x": 0, "y": 0}
        pending_refresh = {"after": None}
        # La foto se prepara una vez por apertura. Antes se recalculaba en cada movimiento del mouse.
        sample_photo, sample_item = self._designer_sample_photo()

        numeric = {"width", "height", "header_height", "title_x", "title_y", "title_size", "photo_x", "photo_y", "photo_w", "photo_h", "name_x", "name_y", "name_size", "role_x", "role_y", "role_size", "id_x", "id_y", "id_size", "qr_x", "qr_y", "qr_size", "logo_x", "logo_y", "logo_w", "logo_h", "name_max_w", "role_max_w", "id_max_w"}

        def values() -> dict:
            result = dict(state)
            for key, variable in variables.items():
                raw = variable.get().strip()
                if key in numeric:
                    try:
                        result[key] = max(0, int(raw))
                    except ValueError:
                        result[key] = state[key]
                else:
                    result[key] = raw
            result["qr_enabled"] = qr_var.get()
            result["header_enabled"] = header_var.get()
            result["auto_fit_text"] = auto_fit_var.get()
            result["shapes"] = shapes
            result["title_visible"] = title_visible_var.get()
            result["name_visible"] = name_visible_var.get()
            result["role_visible"] = role_visible_var.get()
            result["id_visible"] = id_visible_var.get()
            result["custom_texts"] = custom_texts
            return result

        def bounds(template: dict, scale: float) -> dict[str, tuple[float, float, float, float]]:
            result = {
                "Foto": (template["photo_x"] * scale, template["photo_y"] * scale, (template["photo_x"] + template["photo_w"]) * scale, (template["photo_y"] + template["photo_h"]) * scale),
                "Nombre": (template["name_x"] * scale, template["name_y"] * scale, (template["name_x"] + 380) * scale, (template["name_y"] + 45) * scale),
                "Cargo": (template["role_x"] * scale, template["role_y"] * scale, (template["role_x"] + 320) * scale, (template["role_y"] + 40) * scale),
                "ID": (template["id_x"] * scale, template["id_y"] * scale, (template["id_x"] + 240) * scale, (template["id_y"] + 34) * scale),
                "QR": (template["qr_x"] * scale, template["qr_y"] * scale, (template["qr_x"] + template["qr_size"]) * scale, (template["qr_y"] + template["qr_size"]) * scale),
                "Logo": (template["logo_x"] * scale, template["logo_y"] * scale, (template["logo_x"] + template["logo_w"]) * scale, (template["logo_y"] + template["logo_h"]) * scale),
                "Título": (template["title_x"] * scale, template["title_y"] * scale, (template["title_x"] + 330) * scale, (template["title_y"] + 46) * scale),
            }
            for index, shape in enumerate(shapes, start=1):
                result[f"Figura {index}"] = (shape.get("x", 0) * scale, shape.get("y", 0) * scale, (shape.get("x", 0) + shape.get("w", 1)) * scale, (shape.get("y", 0) + shape.get("h", 1)) * scale)
            for index, entry in enumerate(custom_texts, start=1):
                result[f"Texto {index}"] = (entry.get("x", 0) * scale, entry.get("y", 0) * scale, (entry.get("x", 0) + entry.get("max_w", 260)) * scale, (entry.get("y", 0) + max(20, entry.get("size", 20) + 12)) * scale)
            return result

        def render_preview() -> None:
            pending_refresh["after"] = None
            template = values()
            card = self.render_card(sample_photo, sample_item, template)
            available_w, available_h = max(canvas.winfo_width() - 30, 300), max(canvas.winfo_height() - 30, 220)
            scale = min(available_w / card.width, available_h / card.height)
            view = card.resize((max(1, round(card.width * scale)), max(1, round(card.height * scale))), Image.Resampling.LANCZOS)
            image = ImageTk.PhotoImage(view)
            preview_ref["image"] = image
            preview_ref["scale"] = scale
            preview_ref["template"] = template
            canvas.delete("all")
            origin_x, origin_y = (canvas.winfo_width() - view.width) // 2, (canvas.winfo_height() - view.height) // 2
            preview_ref["origin"] = (origin_x, origin_y)
            canvas.create_image(origin_x, origin_y, image=image, anchor="nw")
            box = bounds(template, scale).get(selected.get())
            # La foto ya se reconoce visualmente: no se le superpone un recuadro de selección.
            if box and selected.get() != "Foto":
                canvas.create_rectangle(origin_x + box[0], origin_y + box[1], origin_x + box[2], origin_y + box[3], outline="#43c6db", width=2, dash=(5, 3))

        def refresh(*_args, immediate: bool = False) -> None:
            """Agrupa cambios rápidos del arrastre en una única recomposición de la vista previa."""
            scheduled = pending_refresh.get("after")
            if scheduled is not None:
                try:
                    window.after_cancel(scheduled)
                except tk.TclError:
                    pass
            if immediate:
                render_preview()
            else:
                pending_refresh["after"] = window.after(80, render_preview)

        def choose_element(_event=None) -> None:
            fonts = {"Título": "title_font", "Nombre": "name_font", "Cargo": "role_font", "ID": "id_font"}
            if selected.get() in fonts:
                font_choice.set(variables[fonts[selected.get()]].get())
            sync_inspector()
            refresh(immediate=True)

        def press(event) -> None:
            template = preview_ref.get("template", values())
            scale = preview_ref.get("scale", 1.0)
            origin_x, origin_y = preview_ref.get("origin", (0, 0))
            local_x, local_y = event.x - origin_x, event.y - origin_y
            for name, box in bounds(template, scale).items():
                if box[0] <= local_x <= box[2] and box[1] <= local_y <= box[3]:
                    selected.set(name)
                    break
            drag["x"], drag["y"] = event.x, event.y
            sync_inspector()
            refresh()

        def move(event) -> None:
            if not preview_ref:
                return
            scale = preview_ref.get("scale", 1.0)
            dx, dy = round((event.x - drag["x"]) / scale), round((event.y - drag["y"]) / scale)
            if not dx and not dy:
                return
            mapping = {"Foto": ("photo_x", "photo_y"), "Nombre": ("name_x", "name_y"), "Cargo": ("role_x", "role_y"), "ID": ("id_x", "id_y"), "QR": ("qr_x", "qr_y"), "Logo": ("logo_x", "logo_y"), "Título": ("title_x", "title_y")}
            custom = selected_custom_text()
            if custom is not None:
                custom["x"] = max(0, int(custom.get("x", 0)) + dx)
                custom["y"] = max(0, int(custom.get("y", 0)) + dy)
                drag["x"], drag["y"] = event.x, event.y
                refresh()
                return
            if selected.get().startswith("Figura "):
                index = int(selected.get().split()[-1]) - 1
                if not 0 <= index < len(shapes):
                    return
                shapes[index]["x"] = max(0, int(shapes[index].get("x", 0)) + dx)
                shapes[index]["y"] = max(0, int(shapes[index].get("y", 0)) + dy)
                drag["x"], drag["y"] = event.x, event.y
                refresh()
                return
            x_key, y_key = mapping[selected.get()]
            try:
                variables[x_key].set(str(max(0, int(variables[x_key].get()) + dx)))
                variables[y_key].set(str(max(0, int(variables[y_key].get()) + dy)))
            except ValueError:
                return
            drag["x"], drag["y"] = event.x, event.y
            refresh()

        background_info = ctk.CTkLabel(controls, text="Sin imagen de fondo", text_color=self.MUTED, font=ctk.CTkFont(size=11), wraplength=300, justify="left")
        export_format = tk.StringVar(value="JPG")
        export_folder = tk.StringVar(value=self.output_dir_var.get())

        def choose_background() -> None:
            path = filedialog.askopenfilename(title="Elegir imagen de fondo", filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Todos", "*.*")])
            if path:
                variables["background_image"].set(path)
                background_info.configure(text=f"Fondo: {Path(path).name}")
                refresh()

        def remove_background() -> None:
            variables["background_image"].set("")
            background_info.configure(text="Sin imagen de fondo")
            refresh()

        def choose_designer_logo() -> None:
            path = filedialog.askopenfilename(title="Importar logo", filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Todos", "*.*")])
            if path:
                variables["logo_path"].set(path)
                selected.set("Logo")
                refresh(immediate=True)

        def choose_export_folder() -> None:
            folder = filedialog.askdirectory(title="Carpeta para exportar credenciales", initialdir=export_folder.get() or self.output_dir_var.get() or None)
            if folder:
                export_folder.set(folder)
                self.output_dir_var.set(folder)

        def export_cards(export_all: bool) -> None:
            folder = export_folder.get().strip()
            if not folder:
                choose_export_folder()
                folder = export_folder.get().strip()
            if not folder:
                return
            ok, message = self.export_designer_cards(values(), export_all, export_format.get(), Path(folder))
            if ok:
                self.status_var.set(message)
                messagebox.showinfo("Credenciales exportadas", message)
            else:
                messagebox.showerror("No se pudo exportar", message)

        def pick_color(key: str) -> None:
            current = variables[key].get()
            selected_color = colorchooser.askcolor(color=current, parent=window, title="Elegir color")[1]
            if selected_color:
                variables[key].set(selected_color)
                refresh()

        def update_element_menu() -> None:
            choices = ["Foto", "Nombre", "Cargo", "ID", "QR", "Logo", "Título", *[f"Texto {index}" for index in range(1, len(custom_texts) + 1)], *[f"Figura {index}" for index in range(1, len(shapes) + 1)]]
            element_menu.configure(values=choices)
            if selected.get() not in choices:
                selected.set(choices[-1])

        def selected_shape() -> dict | None:
            if not selected.get().startswith("Figura "):
                return None
            index = int(selected.get().split()[-1]) - 1
            return shapes[index] if 0 <= index < len(shapes) else None

        def selected_custom_text() -> dict | None:
            if not selected.get().startswith("Texto "):
                return None
            index = int(selected.get().split()[-1]) - 1
            return custom_texts[index] if 0 <= index < len(custom_texts) else None

        def nudge(dx: int, dy: int) -> None:
            shape = selected_shape()
            custom = selected_custom_text()
            if custom is not None:
                custom["x"] = max(0, int(custom.get("x", 0)) + dx)
                custom["y"] = max(0, int(custom.get("y", 0)) + dy)
            elif shape is not None:
                shape["x"] = max(0, int(shape.get("x", 0)) + dx)
                shape["y"] = max(0, int(shape.get("y", 0)) + dy)
            else:
                mapping = {"Foto": ("photo_x", "photo_y"), "Nombre": ("name_x", "name_y"), "Cargo": ("role_x", "role_y"), "ID": ("id_x", "id_y"), "QR": ("qr_x", "qr_y"), "Logo": ("logo_x", "logo_y"), "Título": ("title_x", "title_y")}
                x_key, y_key = mapping[selected.get()]
                variables[x_key].set(str(max(0, int(variables[x_key].get()) + dx)))
                variables[y_key].set(str(max(0, int(variables[y_key].get()) + dy)))
            refresh()

        def resize_selected(delta: int) -> None:
            shape = selected_shape()
            custom = selected_custom_text()
            if custom is not None:
                custom["size"] = max(8, int(custom.get("size", 20)) + delta)
            elif shape is not None:
                shape["w"] = max(10, int(shape.get("w", 100)) + delta)
                shape["h"] = max(10, int(shape.get("h", 70)) + delta)
            else:
                mapping = {"Foto": ("photo_w", "photo_h"), "QR": ("qr_size",), "Logo": ("logo_w", "logo_h"), "Título": ("title_size",), "Nombre": ("name_size",), "Cargo": ("role_size",), "ID": ("id_size",)}
                keys = mapping[selected.get()]
                for key in keys:
                    variables[key].set(str(max(8, int(variables[key].get()) + delta)))
            refresh()

        def add_shape() -> None:
            shapes.append({"type": shape_type.get(), "x": 80, "y": 80, "w": 220, "h": 100, "fill": shape_color.get(), "outline": shape_color.get(), "stroke": 1, "z": 30})
            update_element_menu()
            selected.set(f"Figura {len(shapes)}")
            refresh()

        def add_custom_text() -> None:
            text = custom_text_value.get().strip() or "Nuevo texto"
            custom_texts.append({"text": text, "x": 430, "y": 340, "size": 22, "max_w": 420, "font": font_choice.get(), "color": "#18374e", "align": "Izquierda", "bold": False, "visible": True, "z": 60})
            update_element_menu()
            selected.set(f"Texto {len(custom_texts)}")
            sync_inspector()
            refresh()

        def delete_selected_text() -> None:
            custom = selected_custom_text()
            if custom is not None:
                custom_texts.remove(custom)
                selected.set("Foto")
                update_element_menu()
                sync_inspector()
                refresh()

        def apply_custom_content(_event=None) -> None:
            custom = selected_custom_text()
            if custom is not None:
                custom["text"] = custom_text_value.get()
                refresh()

        def delete_shape() -> None:
            shape = selected_shape()
            if shape is not None:
                shapes.remove(shape)
                selected.set("Foto")
                update_element_menu()
                refresh()

        def delete_selected_element() -> None:
            visibility = selected_default_visibility()
            if visibility is not None:
                visibility.set(False)
                refresh(immediate=True)
                return
            if selected_custom_text() is not None:
                delete_selected_text()
                return
            delete_shape()

        def change_layer(front: bool) -> None:
            element = selected_shape() or selected_custom_text()
            if element is not None:
                element["z"] = 100 if front else 5
                refresh()

        def step_layer(step: int) -> None:
            element = selected_shape() or selected_custom_text()
            if element is not None:
                element["z"] = max(0, min(100, int(element.get("z", 30)) + step))
                refresh()

        shape_type = tk.StringVar(value="Rectángulo")
        shape_color = tk.StringVar(value="#dbeafe")
        font_choice = tk.StringVar(value="Arial")
        custom_text_value = tk.StringVar(value="Nuevo texto")

        def pick_shape_color() -> None:
            picked = colorchooser.askcolor(color=shape_color.get(), parent=window, title="Elegir color de figura")[1]
            if picked:
                shape_color.set(picked)
                shape = selected_shape()
                if shape is not None:
                    shape["fill"] = picked
                    shape["outline"] = picked
                    refresh()

        def selected_text_key() -> tuple[str, str] | None:
            return {"Título": ("title_color", "title_font"), "Nombre": ("name_color", "name_font"), "Cargo": ("role_color", "role_font"), "ID": ("id_color", "id_font")}.get(selected.get())

        def selected_default_visibility() -> tk.BooleanVar | None:
            return {"Título": title_visible_var, "Nombre": name_visible_var, "Cargo": role_visible_var, "ID": id_visible_var}.get(selected.get())

        def change_text_color() -> None:
            custom = selected_custom_text()
            if custom is not None:
                picked = colorchooser.askcolor(color=custom.get("color", "#18374e"), parent=window, title="Elegir color de texto")[1]
                if picked:
                    custom["color"] = picked
                    refresh()
                return
            keys = selected_text_key()
            if keys is None:
                messagebox.showinfo("Seleccioná un texto", "Elegí Título, Nombre, Cargo o ID antes de cambiar el color.")
                return
            picked = colorchooser.askcolor(color=variables[keys[0]].get(), parent=window, title="Elegir color de texto")[1]
            if picked:
                variables[keys[0]].set(picked)
                visibility = selected_default_visibility()
                if visibility is not None:
                    visibility.set(True)
                refresh(immediate=True)

        def change_text_font(_value=None) -> None:
            custom = selected_custom_text()
            if custom is not None:
                custom["font"] = font_choice.get()
                refresh()
                return
            keys = selected_text_key()
            if keys is not None:
                variables[keys[1]].set(font_choice.get())
                refresh()

        all_font_names = list(self._installed_card_fonts().keys())
        preferred_font_names = [name for name in ("Aptos", "Arial", "Bahnschrift", "Calibri", "Cambria", "Century Gothic", "Georgia", "Segoe UI", "Tahoma", "Trebuchet MS", "Verdana") if name in all_font_names]
        if font_choice.get() not in preferred_font_names:
            preferred_font_names.insert(0, font_choice.get())

        def open_font_picker() -> None:
            """Buscador acotado: evita el desplegable gigante de todas las fuentes."""
            dialog = ctk.CTkToplevel(window)
            dialog.title("Buscar tipografia de Windows")
            dialog.geometry("420x520")
            dialog.minsize(360, 420)
            dialog.transient(window)
            dialog.grab_set()
            query = tk.StringVar(value="")
            ctk.CTkLabel(dialog, text="Buscar tipografia", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=16, pady=(16, 2))
            ctk.CTkLabel(dialog, text="Escribi parte del nombre. Se muestran hasta 24 resultados.", text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(0, 8))
            search = ctk.CTkEntry(dialog, textvariable=query, placeholder_text="Ej.: Montserrat, Arial, Script...")
            search.pack(fill="x", padx=16, pady=(0, 8))
            results = ctk.CTkScrollableFrame(dialog, fg_color=("#f3f6f8", "#252a30"))
            results.pack(fill="both", expand=True, padx=16, pady=(0, 16))

            def pick_font(name: str) -> None:
                if name not in preferred_font_names:
                    font_menu.configure(values=[name, *preferred_font_names])
                font_choice.set(name)
                font_menu.set(name)
                change_text_font()
                dialog.destroy()

            def show_matches(*_args) -> None:
                for child in results.winfo_children():
                    child.destroy()
                text = query.get().strip().casefold()
                if not text:
                    ctk.CTkLabel(results, text="Empeza a escribir para buscar entre las fuentes instaladas.", wraplength=330, justify="left", text_color=self.MUTED).pack(anchor="w", padx=10, pady=10)
                    return
                matches = [name for name in all_font_names if text in name.casefold()][:24]
                if not matches:
                    ctk.CTkLabel(results, text="No se encontraron coincidencias.", text_color=self.MUTED).pack(anchor="w", padx=10, pady=10)
                    return
                for name in matches:
                    ctk.CTkButton(results, text=name, anchor="w", command=lambda selected_name=name: pick_font(selected_name), fg_color="transparent", text_color=self.TEXT, hover_color=self.SECONDARY).pack(fill="x", padx=4, pady=2)

            query.trace_add("write", show_matches)
            search.focus_set()
            show_matches()

        auto_fit_var = tk.BooleanVar(value=bool(state.get("auto_fit_text", True)))
        text_align = tk.StringVar(value="Izquierda")
        fine_x, fine_y, fine_w, fine_h = (tk.DoubleVar(value=0) for _ in range(4))
        fine_busy = {"value": False}
        inspector_ready = {"value": False}

        def selected_geometry() -> tuple[int, int, int, int]:
            shape = selected_shape()
            if shape is not None:
                return (int(shape.get("x", 0)), int(shape.get("y", 0)), int(shape.get("w", 100)), int(shape.get("h", 70)))
            custom = selected_custom_text()
            if custom is not None:
                size = int(custom.get("size", 20))
                return (int(custom.get("x", 0)), int(custom.get("y", 0)), size, size)
            text_keys = selected_text_key()
            if text_keys is not None:
                prefix = {"title_font": "title", "name_font": "name", "role_font": "role", "id_font": "id"}[text_keys[1]]
                return tuple(int(variables[key].get()) for key in (f"{prefix}_x", f"{prefix}_y", f"{prefix}_size", f"{prefix}_size"))
            mapping = {
                "Foto": ("photo_x", "photo_y", "photo_w", "photo_h"),
                "QR": ("qr_x", "qr_y", "qr_size", "qr_size"),
                "Logo": ("logo_x", "logo_y", "logo_w", "logo_h"),
                "TÃ­tulo": ("title_x", "title_y", "title_size", "title_size"),
                "Nombre": ("name_x", "name_y", "name_size", "name_size"),
                "Cargo": ("role_x", "role_y", "role_size", "role_size"),
                "ID": ("id_x", "id_y", "id_size", "id_size"),
            }
            keys = mapping[selected.get()]
            return tuple(int(variables[key].get()) for key in keys)

        def sync_inspector() -> None:
            if not inspector_ready["value"]:
                return
            fine_busy["value"] = True
            x, y, w, h = selected_geometry()
            fine_x.set(x); fine_y.set(y); fine_w.set(w); fine_h.set(h)
            template = values()
            fine_x_slider.configure(to=max(200, int(template["width"])))
            fine_y_slider.configure(to=max(150, int(template["height"])))
            custom = selected_custom_text()
            is_text = selected_text_key() is not None or custom is not None
            shape = selected_shape()
            fine_w_label.configure(text="Tamano" if is_text else "Ancho")
            fine_h_label.configure(text="Tamano" if is_text else "Alto")
            if False and is_text:
                text_align.set(template.get({"TÃ­tulo": "title_align", "Nombre": "name_align", "Cargo": "role_align", "ID": "id_align"}[selected.get()], "Izquierda"))
            if is_text:
                if custom is not None:
                    text_align.set(custom.get("align", "Izquierda"))
                    font_choice.set(custom.get("font", "Arial"))
                    custom_text_value.set(custom.get("text", ""))
                else:
                    prefix = {"title_font": "title", "name_font": "name", "role_font": "role", "id_font": "id"}[selected_text_key()[1]]
                    text_align.set(template.get(f"{prefix}_align", "Izquierda"))
            inspector_hint.configure(text="Texto: el tamano se ajusta automaticamente al espacio." if is_text else "Usa los deslizadores para un ajuste preciso; tambien podes arrastrar el elemento.")
            shape_options.configure(state="normal" if shape is not None else "disabled")
            if shape is not None:
                shape_type.set(shape.get("type", "Rectangulo"))
            fine_busy["value"] = False

        def apply_fine(_value=None) -> None:
            if fine_busy["value"]:
                return
            x, y, w, h = (max(0, round(value.get())) for value in (fine_x, fine_y, fine_w, fine_h))
            shape = selected_shape()
            if shape is not None:
                shape.update(x=x, y=y, w=max(10, w), h=max(10, h))
            else:
                custom = selected_custom_text()
                if custom is not None:
                    custom.update(x=x, y=y, size=max(8, w))
                    refresh()
                    return
                text_keys = selected_text_key()
                if text_keys is not None:
                    prefix = {"title_font": "title", "name_font": "name", "role_font": "role", "id_font": "id"}[text_keys[1]]
                    variables[f"{prefix}_x"].set(str(x)); variables[f"{prefix}_y"].set(str(y)); variables[f"{prefix}_size"].set(str(max(8, w)))
                    refresh()
                    return
                mapping = {
                    "Foto": ("photo_x", "photo_y", "photo_w", "photo_h"),
                    "QR": ("qr_x", "qr_y", "qr_size", "qr_size"),
                    "Logo": ("logo_x", "logo_y", "logo_w", "logo_h"),
                    "TÃ­tulo": ("title_x", "title_y", "title_size", "title_size"),
                    "Nombre": ("name_x", "name_y", "name_size", "name_size"),
                    "Cargo": ("role_x", "role_y", "role_size", "role_size"),
                    "ID": ("id_x", "id_y", "id_size", "id_size"),
                }
                x_key, y_key, w_key, h_key = mapping[selected.get()]
                variables[x_key].set(str(x)); variables[y_key].set(str(y))
                variables[w_key].set(str(max(8, w)))
                if h_key != w_key:
                    variables[h_key].set(str(max(8, h)))
            refresh()

        def apply_alignment(choice: str) -> None:
            custom = selected_custom_text()
            if custom is not None:
                custom["align"] = choice
                refresh()
                return
            text_keys = selected_text_key()
            if text_keys is not None:
                prefix = {"title_font": "title", "name_font": "name", "role_font": "role", "id_font": "id"}[text_keys[1]]
                variables[f"{prefix}_align"].set(choice)
                refresh()
                return
            keys = {"TÃ­tulo": "title_align", "Nombre": "name_align", "Cargo": "role_align", "ID": "id_align"}
            key = keys.get(selected.get())
            if key:
                variables[key].set(choice)
                refresh()

        def apply_auto_fit() -> None:
            refresh()

        def change_selected_shape_type(choice: str) -> None:
            shape = selected_shape()
            if shape is not None:
                shape["type"] = choice
                refresh()

        def layout_photo(side: str) -> None:
            width, height = int(variables["width"].get()), int(variables["height"].get())
            photo_w, photo_h = int(variables["photo_w"].get()), int(variables["photo_h"].get())
            padding = 44
            if side == "izquierda":
                photo_x, text_x, text_w = padding, photo_w + padding * 2, width - photo_w - padding * 3
            else:
                photo_x, text_x, text_w = width - photo_w - padding, padding, width - photo_w - padding * 3
            variables["photo_x"].set(str(max(0, photo_x)))
            variables["photo_y"].set(str(max(105, (height - photo_h) // 2)))
            for prefix, y in (("name", 210), ("role", 270), ("id", 495)):
                variables[f"{prefix}_x"].set(str(max(0, text_x)))
                variables[f"{prefix}_y"].set(str(y))
                variables[f"{prefix}_max_w"].set(str(max(100, text_w)))
            selected.set("Foto")
            sync_inspector()
            refresh(immediate=True)

        canvas.bind("<Configure>", refresh)
        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<B1-Motion>", move)
        ctk.CTkLabel(controls, text="Diseñador de credencial", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=10, pady=(10, 2))
        ctk.CTkLabel(controls, text="Elegí un elemento y arrastralo sobre la tarjeta. Los cambios se ven en tiempo real.", wraplength=300, justify="left", text_color=self.MUTED).pack(anchor="w", padx=10, pady=(0, 10))
        element_menu = ctk.CTkOptionMenu(controls, values=["Foto", "Nombre", "Cargo", "ID", "QR", "Título"], variable=selected, command=lambda _value: choose_element())
        element_menu.pack(fill="x", padx=10, pady=(0, 8))
        update_element_menu()
        ctk.CTkLabel(controls, text="Textos predeterminados", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(2, 2))
        ctk.CTkLabel(controls, text="Ocultalos sin perderlos de la plantilla.", text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)
        default_texts = ctk.CTkFrame(controls, fg_color="transparent")
        default_texts.pack(fill="x", padx=10, pady=(2, 5))
        ctk.CTkCheckBox(default_texts, text="Titulo", variable=title_visible_var, command=refresh).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ctk.CTkCheckBox(default_texts, text="Nombre", variable=name_visible_var, command=refresh).grid(row=0, column=1, sticky="w")
        ctk.CTkCheckBox(default_texts, text="Cargo", variable=role_visible_var, command=refresh).grid(row=1, column=0, sticky="w", padx=(0, 12))
        ctk.CTkCheckBox(default_texts, text="ID", variable=id_visible_var, command=refresh).grid(row=1, column=1, sticky="w")
        ctk.CTkLabel(controls, text="Agregar texto libre", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkLabel(controls, text="Podes usar {nombre}, {cargo} o {id} para mostrar datos de cada persona.", wraplength=300, justify="left", text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)
        custom_entry = ctk.CTkEntry(controls, textvariable=custom_text_value, placeholder_text="Texto nuevo o texto seleccionado")
        custom_entry.pack(fill="x", padx=10, pady=(3, 3))
        custom_entry.bind("<KeyRelease>", apply_custom_content)
        custom_text_row = ctk.CTkFrame(controls, fg_color="transparent")
        custom_text_row.pack(fill="x", padx=10, pady=(0, 7))
        custom_text_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(custom_text_row, text="Agregar texto", command=add_custom_text, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(custom_text_row, text="Eliminar texto", command=delete_selected_text, fg_color=self.DANGER, text_color=self.DANGER_TEXT, hover_color=self.DANGER_HOVER).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ctk.CTkLabel(controls, text="Distribucion automatica", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        ctk.CTkLabel(controls, text="Ordena foto y datos sin calcular coordenadas.", text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(0, 4))
        layout_row = ctk.CTkFrame(controls, fg_color="transparent")
        layout_row.pack(fill="x", padx=10, pady=(0, 9))
        layout_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(layout_row, text="Foto a la izquierda", command=lambda: layout_photo("izquierda"), fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(layout_row, text="Foto a la derecha", command=lambda: layout_photo("derecha"), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ctk.CTkFrame(controls, height=2, fg_color=("#dce5ec", "#3b4148")).pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkLabel(controls, text="Ajuste del elemento", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10)
        inspector_hint = ctk.CTkLabel(controls, text="Arrastra el elemento o usa los deslizadores.", wraplength=300, justify="left", text_color=self.MUTED, font=ctk.CTkFont(size=11))
        inspector_hint.pack(anchor="w", padx=10, pady=(1, 5))
        fine_x_label = ctk.CTkLabel(controls, text="Horizontal", text_color=self.MUTED, font=ctk.CTkFont(size=11)); fine_x_label.pack(anchor="w", padx=10)
        fine_x_slider = ctk.CTkSlider(controls, from_=0, to=1016, variable=fine_x, command=apply_fine, progress_color=self.PURPLE, button_color=self.PURPLE); fine_x_slider.pack(fill="x", padx=10, pady=(0, 3))
        fine_y_label = ctk.CTkLabel(controls, text="Vertical", text_color=self.MUTED, font=ctk.CTkFont(size=11)); fine_y_label.pack(anchor="w", padx=10)
        fine_y_slider = ctk.CTkSlider(controls, from_=0, to=638, variable=fine_y, command=apply_fine, progress_color=self.PURPLE, button_color=self.PURPLE); fine_y_slider.pack(fill="x", padx=10, pady=(0, 3))
        fine_w_label = ctk.CTkLabel(controls, text="Ancho", text_color=self.MUTED, font=ctk.CTkFont(size=11)); fine_w_label.pack(anchor="w", padx=10)
        fine_w_slider = ctk.CTkSlider(controls, from_=8, to=700, variable=fine_w, command=apply_fine, progress_color=self.PURPLE, button_color=self.PURPLE); fine_w_slider.pack(fill="x", padx=10, pady=(0, 3))
        fine_h_label = ctk.CTkLabel(controls, text="Alto", text_color=self.MUTED, font=ctk.CTkFont(size=11)); fine_h_label.pack(anchor="w", padx=10)
        fine_h_slider = ctk.CTkSlider(controls, from_=8, to=650, variable=fine_h, command=apply_fine, progress_color=self.PURPLE, button_color=self.PURPLE); fine_h_slider.pack(fill="x", padx=10, pady=(0, 7))
        movement = ctk.CTkFrame(controls, fg_color="transparent")
        movement.pack(fill="x", padx=10, pady=(0, 8))
        for column in range(3):
            movement.grid_columnconfigure(column, weight=1)
        ctk.CTkButton(movement, text="↑", width=36, command=lambda: nudge(0, -10), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=0, column=1, padx=2, pady=2)
        ctk.CTkButton(movement, text="←", width=36, command=lambda: nudge(-10, 0), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=1, column=0, padx=2, pady=2)
        ctk.CTkButton(movement, text="→", width=36, command=lambda: nudge(10, 0), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=1, column=2, padx=2, pady=2)
        ctk.CTkButton(movement, text="↓", width=36, command=lambda: nudge(0, 10), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=2, column=1, padx=2, pady=2)
        size_row = ctk.CTkFrame(controls, fg_color="transparent")
        size_row.pack(fill="x", padx=10, pady=(0, 8))
        size_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(size_row, text="− Tamaño", command=lambda: resize_selected(-10), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(size_row, text="+ Tamaño", command=lambda: resize_selected(10), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ctk.CTkLabel(controls, text="Tipografia", text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)
        font_menu = ctk.CTkOptionMenu(controls, values=preferred_font_names, variable=font_choice, command=change_text_font)
        font_menu.pack(fill="x", padx=10, pady=(2, 3))
        ctk.CTkButton(controls, text="Buscar otra tipografia de Windows", command=open_font_picker, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).pack(fill="x", padx=10, pady=(0, 3))
        ctk.CTkButton(controls, text="Elegir color de texto", command=change_text_color, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkLabel(controls, text="Alineacion del texto", text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)
        ctk.CTkOptionMenu(controls, values=["Izquierda", "Centro", "Derecha"], variable=text_align, command=apply_alignment).pack(fill="x", padx=10, pady=(2, 3))
        ctk.CTkCheckBox(controls, text="Reducir texto largo automaticamente", variable=auto_fit_var, command=apply_auto_fit).pack(anchor="w", padx=10, pady=(0, 8))
        ctk.CTkLabel(controls, text="Figuras y capas", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(4, 2))
        shape_options = ctk.CTkOptionMenu(controls, values=["Rectángulo", "Círculo", "Línea"], variable=shape_type, command=change_selected_shape_type)
        shape_options.pack(fill="x", padx=10, pady=(0, 3))
        ctk.CTkButton(controls, text="Elegir color de figura", command=lambda: pick_shape_color(), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).pack(fill="x", padx=10, pady=(0, 3))
        shape_row = ctk.CTkFrame(controls, fg_color="transparent")
        shape_row.pack(fill="x", padx=10, pady=(0, 3))
        shape_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(shape_row, text="Agregar figura", command=add_shape, fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(shape_row, text="Eliminar seleccionado", command=delete_selected_element, fg_color=self.DANGER, text_color=self.DANGER_TEXT, hover_color=self.DANGER_HOVER).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        layer_row = ctk.CTkFrame(controls, fg_color="transparent")
        layer_row.pack(fill="x", padx=10, pady=(0, 8))
        layer_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(layer_row, text="Al fondo", command=lambda: change_layer(False), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(layer_row, text="Al frente", command=lambda: change_layer(True), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ctk.CTkButton(layer_row, text="Bajar una capa", command=lambda: step_layer(-10), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=1, column=0, sticky="ew", padx=(0, 3), pady=(4, 0))
        ctk.CTkButton(layer_row, text="Subir una capa", command=lambda: step_layer(10), fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).grid(row=1, column=1, sticky="ew", padx=(3, 0), pady=(4, 0))
        ctk.CTkCheckBox(controls, text="Mostrar QR", variable=qr_var, command=refresh).pack(anchor="w", padx=10, pady=(0, 8))
        ctk.CTkCheckBox(controls, text="Mostrar franja superior", variable=header_var, command=refresh).pack(anchor="w", padx=10, pady=(0, 8))
        ctk.CTkLabel(controls, text="Imagen de fondo", text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)
        ctk.CTkButton(controls, text="Importar imagen de fondo", command=choose_background, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).pack(fill="x", padx=10, pady=(2, 3))
        background_info.configure(text=f"Fondo: {Path(variables['background_image'].get()).name}" if variables["background_image"].get() else "Sin imagen de fondo")
        background_info.pack(anchor="w", padx=10)
        ctk.CTkButton(controls, text="Quitar imagen de fondo", command=remove_background, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).pack(fill="x", padx=10, pady=(3, 8))
        ctk.CTkLabel(controls, text="Logo", text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)
        ctk.CTkButton(controls, text="Importar o reemplazar logo", command=choose_designer_logo, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).pack(fill="x", padx=10, pady=(2, 8))
        labels = [("width", "Ancho de tarjeta"), ("height", "Alto de tarjeta"), ("background", "Color de fondo"), ("header_height", "Alto de franja"), ("header_color", "Color de franja"), ("title", "Título"), ("title_size", "Tamaño título"), ("photo_w", "Ancho foto"), ("photo_h", "Alto foto"), ("name_size", "Tamaño nombre"), ("role_size", "Tamaño cargo"), ("id_size", "Tamaño ID"), ("qr_size", "Tamaño QR")]
        for key, label in labels:
            ctk.CTkLabel(controls, text=label, text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(5, 0))
            entry = ctk.CTkEntry(controls, textvariable=variables[key])
            entry.pack(fill="x", padx=10)
            entry.bind("<KeyRelease>", refresh)
        ctk.CTkLabel(controls, text="Posición del elemento seleccionado", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(12, 2))
        ctk.CTkLabel(controls, text="Arrastrá sobre la vista previa para modificarla. Las coordenadas se guardan dentro de la plantilla.", wraplength=300, justify="left", text_color=self.MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10)

        def save() -> None:
            self.card_template = values()
            self.brand_name_var.set(self.card_template["title"])
            self.brand_color_var.set(self.card_template["header_color"])
            self._save_card_template()
            self.status_var.set("Plantilla de credencial guardada.")
            window.destroy()

        def reset() -> None:
            for key, value in self.DEFAULT_CARD_TEMPLATE.items():
                if key == "qr_enabled":
                    qr_var.set(bool(value))
                elif key == "header_enabled":
                    header_var.set(bool(value))
                elif key == "auto_fit_text":
                    auto_fit_var.set(bool(value))
                elif key == "title_visible":
                    title_visible_var.set(bool(value))
                elif key == "name_visible":
                    name_visible_var.set(bool(value))
                elif key == "role_visible":
                    role_visible_var.set(bool(value))
                elif key == "id_visible":
                    id_visible_var.set(bool(value))
                elif key == "shapes":
                    shapes.clear()
                elif key == "custom_texts":
                    custom_texts.clear()
                else:
                    variables[key].set(str(value))
            background_info.configure(text="Sin imagen de fondo")
            update_element_menu()
            sync_inspector()
            refresh()

        ctk.CTkFrame(controls, height=2, fg_color=("#dce5ec", "#3b4148")).pack(fill="x", padx=10, pady=(15, 8))
        ctk.CTkLabel(controls, text="Exportar desde el diseñador", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10)
        ctk.CTkOptionMenu(controls, values=["JPG", "PNG", "WEBP", "PDF"], variable=export_format).pack(fill="x", padx=10, pady=(4, 4))
        ctk.CTkButton(controls, text="Elegir carpeta de exportación", command=choose_export_folder, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(controls, textvariable=export_folder, wraplength=300, justify="left", text_color=self.MUTED, font=ctk.CTkFont(size=10)).pack(anchor="w", padx=10)
        export_row = ctk.CTkFrame(controls, fg_color="transparent")
        export_row.pack(fill="x", padx=10, pady=(5, 10))
        export_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(export_row, text="Exportar actual", command=lambda: export_cards(False), fg_color=("#11806a", "#218c78"), hover_color=("#0c6655", "#176c5c")).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(export_row, text="Exportar lote", command=lambda: export_cards(True), fg_color=self.PURPLE, hover_color=self.PURPLE_HOVER).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        ctk.CTkButton(controls, text="Guardar plantilla", command=save, fg_color=("#11806a", "#218c78"), hover_color=("#0c6655", "#176c5c"), font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=10, pady=(15, 5))
        ctk.CTkButton(controls, text="Restablecer diseño", command=reset, fg_color=self.SECONDARY, text_color=self.SECONDARY_TEXT, hover_color=self.SECONDARY_HOVER).pack(fill="x", padx=10, pady=(0, 12))
        inspector_ready["value"] = True
        sync_inspector()
        window.after(120, refresh)

    def choose_brand_logo(self) -> None:
        path = filedialog.askopenfilename(title="Elegir logo para la tarjeta", filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")])
        if not path:
            return
        self.brand_logo_path = Path(path)
        self.status_var.set(f"Logo seleccionado: {self.brand_logo_path.name}")

    def _export_validation_messages(self, items: list[PhotoItem] | None = None) -> list[str]:
        items = self.photos if items is None else items
        warnings = []
        if not items:
            return ["No hay fotos cargadas."]
        pending = [item for item in items if self.needs_review(item)]
        if pending:
            warnings.append(f"{len(pending)} foto(s) requieren revisión antes de exportar.")
        if not self.output_dir_var.get().strip():
            warnings.append("No se eligió una carpeta de salida.")
        template = self.name_template_var.get().strip() or "{nombre}{sufijo}"
        try:
            template.format(nombre="foto", sufijo="", fecha=date.today().isoformat())
        except (KeyError, ValueError):
            warnings.append("La plantilla de nombre contiene un campo inválido.")
        if self.template_var.get() == "Tarjeta simple" and not re.fullmatch(r"#[0-9a-fA-F]{6}", self.brand_color_var.get().strip()):
            warnings.append("El color institucional no es válido; se usará el color predeterminado.")
        names = set()
        duplicates = 0
        for item in items:
            try:
                name = template.format(nombre=item.path.stem, sufijo=self.suffix_var.get().strip(), fecha=date.today().isoformat()).casefold()
            except (KeyError, ValueError):
                break
            if name in names:
                duplicates += 1
            names.add(name)
        if duplicates:
            warnings.append(f"{duplicates} nombre(s) de salida se repetirían; se agregarán números automáticamente.")
        return warnings

    def show_export_validation(self) -> None:
        warnings = self._export_validation_messages()
        if warnings:
            messagebox.showwarning("Validación de exportación", "\n".join(f"• {warning}" for warning in warnings))
            self.status_var.set("La exportación tiene observaciones.")
        else:
            messagebox.showinfo("Validación de exportación", "Todo está listo: no se detectaron observaciones antes de exportar.")
            self.status_var.set("Lote validado y listo para exportar.")

    def auto_light_dark_only(self) -> None:
        if not self.photos:
            messagebox.showinfo("Sin fotos", "Cargá fotos antes de aplicar una regla de lote.")
            return
        adjusted = 0
        for item in self.photos:
            mean = float(np.asarray(item.image.convert("L"), dtype=np.float32).mean())
            if mean < 90:
                self.snapshot_item(item)
                item.brightness = min(1.40, max(1.05, 128 / max(mean, 1)))
                item.contrast = max(item.contrast, 1.05)
                adjusted += 1
        self.sync_adjustment_controls()
        self.rebuild_list()
        self.refresh_preview()
        self.status_var.set(f"Auto luz aplicada a {adjusted} foto(s) oscuras.")
        messagebox.showinfo("Auto luz por lote", f"Se ajustaron {adjusted} foto(s) con brillo bajo. Las demás no se modificaron.")

    def export_contact_sheet_pdf(self) -> None:
        if not self.photos:
            messagebox.showinfo("Sin fotos", "Cargá fotos para generar la hoja de revisión.")
            return
        folder = Path(self.output_dir_var.get()) if self.output_dir_var.get().strip() else self.preset_path.parent
        try:
            folder.mkdir(parents=True, exist_ok=True)
            pages = []
            page_width, page_height = 1654, 2339
            columns, rows = 3, 5
            cell_width, cell_height = page_width // columns, 420
            margin_top = 115
            font = ImageFont.load_default()
            for first in range(0, len(self.photos), columns * rows):
                page = Image.new("RGB", (page_width, page_height), "white")
                draw = ImageDraw.Draw(page)
                draw.rectangle((0, 0, page_width, 72), fill="#0c5e91")
                draw.text((28, 24), f"HOJA DE REVISION · {date.today().isoformat()}", fill="white", font=font)
                for position, item in enumerate(self.photos[first:first + columns * rows]):
                    column, row = position % columns, position // columns
                    x, y = column * cell_width + 24, margin_top + row * cell_height
                    preview = self.adjusted_image(item).crop(tuple(round(value) for value in item.crop)).convert("RGB")
                    preview.thumbnail((cell_width - 48, 310), Image.Resampling.LANCZOS)
                    page.paste(preview, (x + (cell_width - 48 - preview.width) // 2, y))
                    status = self.photo_status(item)
                    name = item.path.name.encode("ascii", "replace").decode("ascii")
                    label = f"{first + position + 1}. {name[:55]}\n{status[:65]}"
                    draw.multiline_text((x, y + 325), label, fill="#18374e", font=font, spacing=4)
                pages.append(page)
            destination = folder / f"hoja_revision_{datetime.now():%Y%m%d_%H%M%S}.pdf"
            pages[0].save(destination, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
        except OSError as error:
            messagebox.showerror("No se pudo crear el PDF", str(error))
            return
        self.status_var.set(f"Hoja PDF de revisión creada: {destination.name}")
        messagebox.showinfo("Hoja de revisión creada", f"Se guardó en:\n{destination}")

    def _write_batch_log(self, output_dir: Path, records: list[tuple[PhotoItem, Path]]) -> None:
        if not records:
            return
        log = output_dir / f"registro_lote_{datetime.now():%Y%m%d_%H%M%S}.csv"
        try:
            with log.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["Fecha y hora", "Archivo origen", "Archivo exportado", "Estado"])
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for item, exported in records:
                    writer.writerow([stamp, item.path.name, exported.name, self.photo_status(item)])
        except OSError:
            pass

    def clear_sensitive_data(self) -> None:
        if not messagebox.askyesno("Limpiar datos locales", "Se eliminarán datos CSV/Excel cargados, rutas recordadas y caché de esta sesión. Las fotos y planillas originales no se borran. ¿Continuar?"):
            return
        self.metadata.clear()
        self.excel_rows.clear()
        self.excel_headers.clear()
        self.excel_path = None
        self.quality_results.clear()
        self._preview_masks.clear()
        self.last_export_paths.clear()
        self.output_dir_var.set("")
        self.last_input_dir = ""
        try:
            self.session_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.excel_result.configure(text="Datos de Excel eliminados de esta sesión.")
        self.status_var.set("Datos locales de esta sesión eliminados.")

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
            template.format(nombre="foto", sufijo="", fecha=date.today().isoformat())
        except (KeyError, ValueError) as error:
            messagebox.showerror("Plantilla inválida", str(error))
            return
        items = self.photos if export_all else ([self.get_current()] if self.get_current() else [])
        if not items:
            return
        warnings = [warning for warning in self._export_validation_messages(items) if warning != "No se eligió una carpeta de salida."]
        if warnings and not messagebox.askyesno("Observaciones antes de exportar", "Se detectaron estas observaciones:\n\n" + "\n".join(f"• {warning}" for warning in warnings) + "\n\n¿Exportar de todos modos?"):
            self.status_var.set("Exportación cancelada para revisar observaciones.")
            return
        extension, pil_format = EXPORT_FORMATS[self.format_var.get()]
        records: list[tuple[PhotoItem, Path]] = []
        for number, item in enumerate(items, start=1):
            left, top, _right, _bottom = item.crop
            image = self.adjusted_image(item).crop(tuple(round(value) for value in item.crop))
            face_box = None
            if item.face_box:
                x, y, w, h = item.face_box
                face_box = (int(x - left), int(y - top), w, h)
            image = self.process_background(image, item, face_box)
            size = self.get_output_size(item.crop)
            if (self.width_var.get().strip() or self.height_var.get().strip()) and size is None:
                return
            if size:
                image = image.resize(size, Image.Resampling.LANCZOS)
            if self.template_var.get() == "Tarjeta simple":
                image = self.make_card(image, item)
            name = template.format(nombre=item.path.stem, sufijo=self.suffix_var.get().strip(), fecha=date.today().isoformat())
            name = re.sub(r'[<>:"/\\|?*]+', "_", name).strip(". ") or item.path.stem
            destination = self.available_path(output_dir / f"{name}{extension}")
            try:
                if pil_format == "JPEG":
                    image.convert("RGB").save(destination, "JPEG", quality=95, optimize=True)
                elif pil_format == "PNG":
                    image.save(destination, "PNG", optimize=True)
                else:
                    image.save(destination, pil_format)
            except OSError as error:
                messagebox.showerror("Error al exportar", f"No se pudo guardar {item.path.name}: {error}")
                return
            records.append((item, destination))
            self.status_var.set(f"Exportando {number} de {len(items)}…")
            self.root.update_idletasks()
        self.last_export_paths = [destination for _item, destination in records]
        self._write_batch_log(output_dir, records)
        self.status_var.set(f"Listo: se exportaron {len(items)} foto(s) y se registró el lote en {output_dir}.")
        messagebox.showinfo("Exportación terminada", f"Se exportaron {len(items)} foto(s). También se creó un registro CSV del lote.")


if __name__ == "__main__":
    RecortadorAvanzado().run()
