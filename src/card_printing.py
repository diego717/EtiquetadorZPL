"""Impresión directa de credenciales en impresoras de tarjetas (Windows).

Se imprime a través del controlador de cada marca (Zebra, Magicard, Entrust,
Swiftpro, Evolis...), igual que lo hacen CardExchange o TrustID: cada cara de
la credencial es una página y, en doble faz, el controlador junta las páginas
de a dos sobre la misma tarjeta.

Cada controlador declara una página algo distinta (Magicard 1016×642 px
horizontal, Entrust y Swiftpro verticales con sangrado de retransferencia), así
que en cada trabajo se fija la orientación y la doble faz, se gira la imagen si
el controlador no respetó la orientación pedida y se cubre la página completa.
Ribbon, panel negro (K), overlay y calidad se toman de las preferencias del
controlador en Windows.
"""

from __future__ import annotations

import csv
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps, ImageWin

CARD_PRINTER_PATTERN = re.compile(
    r"zebra|zxp|\bzc ?[1-3]\d\d|magicard|enduro|rio ?pro|600 ?neo|300 ?neo|pronto|ultima|entrust|datacard|"
    r"xps card|sigma|\bcd ?8\d\d|\bcr ?8\d\d|swift ?pro|evolis|primacy|zenius|fargo|\bdtc ?\d|\bhdp ?\d|"
    r"idp smart|card printer",
    re.IGNORECASE,
)
PRINTER_STATUS = {
    0x00000080: "Sin conexión",
    0x00000002: "Con error",
    0x00000008: "Atasco de tarjeta",
    0x00000010: "Sin tarjetas",
    0x00000001: "En pausa",
    0x00400000: "Puerta abierta",
    0x00040000: "Sin ribbon",
}
DMDUP_SIMPLEX, DMDUP_VERTICAL = 1, 2
DMORIENT_PORTRAIT, DMORIENT_LANDSCAPE = 1, 2
DM_ORIENTATION, DM_DUPLEX = 0x00000001, 0x00001000
DM_IN_BUFFER, DM_OUT_BUFFER = 8, 2
PHYSICALWIDTH, PHYSICALHEIGHT, PHYSICALOFFSETX, PHYSICALOFFSETY, LOGPIXELSX = 110, 111, 112, 113, 88

PRINT_LOCK = threading.Lock()
_CATALOG_LOCK = threading.Lock()
_CATALOG: tuple[float, list[dict]] | None = None


class CardPrintError(RuntimeError):
    """Error del spooler o del controlador, con un mensaje para el usuario."""


def _win32():
    try:
        import win32gui
        import win32print
        import win32ui
    except ImportError as exc:  # pragma: no cover - sólo fuera de Windows
        raise CardPrintError("La impresión directa sólo está disponible en Windows con pywin32") from exc
    return win32print, win32gui, win32ui


def status_text(status: int) -> str:
    for flag, label in PRINTER_STATUS.items():
        if status & flag:
            return label
    return "Lista"


def is_card_printer(name: str, driver: str) -> bool:
    return bool(CARD_PRINTER_PATTERN.search(f"{name} {driver}"))


def list_printers(max_age: float = 30.0) -> list[dict]:
    """Impresoras instaladas; primero las de tarjetas. Se cachea unos segundos."""
    global _CATALOG
    with _CATALOG_LOCK:
        if _CATALOG and time.monotonic() - _CATALOG[0] < max_age:
            return _CATALOG[1]
        win32print, _gui, _ui = _win32()
        try:
            default = win32print.GetDefaultPrinter()
        except Exception:
            default = ""
        printers = []
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        for entry in win32print.EnumPrinters(flags, None, 2):
            name = entry["pPrinterName"]
            driver = entry.get("pDriverName") or ""
            printers.append({
                "name": name,
                "driver": driver,
                "card": is_card_printer(name, driver),
                "default": name == default,
                "status": status_text(int(entry.get("Status") or 0)),
                "ready": not int(entry.get("Status") or 0) & 0x00000080,
            })
        printers.sort(key=lambda item: (not item["card"], item["name"].casefold()))
        _CATALOG = (time.monotonic(), printers)
        return printers


def invalidate_catalog() -> None:
    global _CATALOG
    with _CATALOG_LOCK:
        _CATALOG = None


@dataclass
class PageGeometry:
    width: int
    height: int
    offset_x: int
    offset_y: int
    dpi: int


class CardPrintJob:
    """Trabajo de impresión: una página por cara, en el orden frente, dorso."""

    def __init__(self, printer: str, *, landscape: bool, duplex: bool, title: str, output_file: str | None = None) -> None:
        self.printer = printer
        self.landscape = landscape
        self.duplex = duplex
        self.title = title[:120] or "Credenciales"
        self.output_file = output_file
        self.pages = 0
        self._dc = None
        self._hdc = None
        self.geometry: PageGeometry | None = None

    def __enter__(self) -> "CardPrintJob":
        win32print, win32gui, win32ui = _win32()
        try:
            handle = win32print.OpenPrinter(self.printer)
        except Exception as exc:
            raise CardPrintError(f"No se encontró la impresora “{self.printer}”") from exc
        try:
            devmode = win32print.GetPrinter(handle, 2)["pDevMode"]
            if devmode is not None:
                devmode.Orientation = DMORIENT_LANDSCAPE if self.landscape else DMORIENT_PORTRAIT
                devmode.Duplex = DMDUP_VERTICAL if self.duplex else DMDUP_SIMPLEX
                devmode.Fields = devmode.Fields | DM_ORIENTATION | DM_DUPLEX
                try:
                    # Deja que el controlador valide y complete su parte privada.
                    win32print.DocumentProperties(0, handle, self.printer, devmode, devmode, DM_IN_BUFFER | DM_OUT_BUFFER)
                except Exception:
                    pass
            self._hdc = win32gui.CreateDC("WINSPOOL", self.printer, devmode)
        except Exception as exc:
            raise CardPrintError(f"El controlador de “{self.printer}” no aceptó el trabajo: {exc}") from exc
        finally:
            win32print.ClosePrinter(handle)
        self._dc = win32ui.CreateDCFromHandle(self._hdc)
        caps = self._dc.GetDeviceCaps
        self.geometry = PageGeometry(
            width=caps(PHYSICALWIDTH), height=caps(PHYSICALHEIGHT),
            offset_x=caps(PHYSICALOFFSETX), offset_y=caps(PHYSICALOFFSETY), dpi=caps(LOGPIXELSX) or 300,
        )
        if self.geometry.width <= 0 or self.geometry.height <= 0:
            self._release()
            raise CardPrintError("El controlador no informó el tamaño de la tarjeta")
        try:
            if self.output_file:
                self._dc.StartDoc(self.title, self.output_file)
            else:
                self._dc.StartDoc(self.title)
        except Exception as exc:
            self._release()
            raise CardPrintError(f"No se pudo iniciar el trabajo en “{self.printer}”: {exc}") from exc
        return self

    @property
    def dpi(self) -> int:
        return self.geometry.dpi if self.geometry else 300

    def add_card(self, faces: Iterable[Image.Image], *, rotate_back: bool = False) -> None:
        for index, face in enumerate(faces):
            image = face.convert("RGB")
            if index == 1 and rotate_back:
                image = image.rotate(180)
            self._page(image)

    def _page(self, image: Image.Image) -> None:
        geometry = self.geometry
        if (image.width > image.height) != (geometry.width > geometry.height):
            # El controlador quedó en la otra orientación: se gira la imagen.
            image = image.rotate(90, expand=True)
        fitted = ImageOps.fit(image, (geometry.width, geometry.height), method=Image.Resampling.LANCZOS)
        self._dc.StartPage()
        ImageWin.Dib(fitted).draw(
            self._dc.GetHandleOutput(),
            (-geometry.offset_x, -geometry.offset_y, geometry.width - geometry.offset_x, geometry.height - geometry.offset_y),
        )
        self._dc.EndPage()
        self.pages += 1

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if exc_type is None:
                self._dc.EndDoc()
            else:
                self._dc.AbortDoc()
        finally:
            self._release()

    def _release(self) -> None:
        if self._dc is not None:
            try:
                self._dc.DeleteDC()
            except Exception:
                pass
        self._dc = None
        self._hdc = None


def log_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home()) / "EtiquetadorZPL" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base / "credenciales_impresas.csv"


def append_print_log(rows: list[list[str]], path: Path | None = None) -> None:
    """Registro permanente de lo impreso, para auditar reimpresiones."""
    target = path or log_path()
    new_file = not target.exists()
    with target.open("a", newline="", encoding="utf-8-sig") as output:
        writer = csv.writer(output)
        if new_file:
            writer.writerow(["Fecha y hora", "Impresora", "Archivo", "Datos", "Caras", "Copias"])
        writer.writerows(rows)


def timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
