"""
Impresion de los documentos de TRABAJOS que antes salian del menu de la planilla:

- Etiqueta de ORDEN (88 x 28 mm) -> etiquetadora (ZPL, sin recortar).
  Diseno de googleScripts/09_EtiquetaOrden.txt.
- Orden de fabricacion / "Orden para TALLER" (A4) -> impresora de ordenes.
  Diseno de googleScripts/10_HojaTrabajo.txt.
- Etiquetas precargadas (PDF de la carpeta de Drive) -> etiquetadora o A4.

El HTML/CSS es el mismo de los scripts y lo dibuja el Chromium de Playwright,
asi que lo impreso queda igual que desde la planilla.
"""

from __future__ import annotations

import html
import io
import logging
import re
import threading
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# La Godex GE300 imprime a 203 dpi: la etiqueta se dibuja a esa resolucion
# para que 1 pixel sea 1 punto y salga a tamano real.
LABEL_DPI = 203
ORDER_LABEL_MM = (88, 28)
CSS_DPI = 96
MAX_IMAGES = 6
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_COPIES = 10

_render_lock = threading.Lock()

DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre",
          "Octubre", "Noviembre", "Diciembre"]
MONTH_ALIASES = {
    "jan": 1, "ene": 1, "feb": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "ago": 8, "sep": 9, "set": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12, "dic": 12,
}


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def format_due_date(due_date: str, due_text: str, today: Optional[date] = None) -> str:
    """Como formatearFechaEntrega: "Martes 13 Octubre"; sin fecha, "-- STOCK --"."""
    parsed: Optional[date] = None
    if due_date:
        try:
            parsed = date.fromisoformat(due_date[:10])
        except ValueError:
            parsed = None
    text = (due_text or "").strip()
    if parsed is None and text:
        parts = [p for p in re.split(r"[-/ ]+", text) if p]
        if len(parts) >= 2 and parts[0].isdigit():
            month = int(parts[1]) if parts[1].isdigit() else MONTH_ALIASES.get(parts[1].lower()[:4]) or MONTH_ALIASES.get(parts[1].lower()[:3])
            year = (today or date.today()).year
            if len(parts) >= 3 and parts[2].isdigit():
                year = int(parts[2]) + (2000 if int(parts[2]) < 100 else 0)
            try:
                parsed = date(year, int(month), int(parts[0])) if month else None
            except ValueError:
                parsed = None
    if parsed is None:
        return _esc(text) if text else "-- STOCK --"
    return f"{DAYS[parsed.weekday()]} {parsed.day} {MONTHS[parsed.month - 1]}"


# ---------------------------------------------------------------- HTML ----

ORDER_LABEL_CSS = """
@page { size: 88mm 28mm; margin: 0; }
html, body { margin: 0; padding: 0; width: 88mm; height: 28mm; font-family: Arial, sans-serif; background: #fff; }
* { box-sizing: border-box; }
.pagina-etiqueta { width: 88mm; height: 28mm; padding: 1.5mm 2mm; display: flex; align-items: center; justify-content: center; }
.contenedor { display: flex; width: 100%; height: 100%; align-items: center; }
.orden { writing-mode: vertical-rl; transform: rotate(180deg); font-size: 18pt; font-weight: bold; text-align: center;
         flex-shrink: 0; margin-right: 2.5mm; display: flex; align-items: center; justify-content: center; }
.datos { flex: 1; display: flex; flex-direction: column; justify-content: space-between; height: 100%; }
.bloque { display: flex; flex-direction: column; justify-content: center; }
.titulo { font-size: 6pt; font-weight: normal; color: #333; margin: 0; line-height: 1; }
.valor { font-size: 8.5pt; font-weight: bold; margin: 0; line-height: 1.1; word-break: break-word; }
"""


def order_label_html(job: Dict[str, Any]) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{ORDER_LABEL_CSS}</style></head><body>
<div class="pagina-etiqueta"><div class="contenedor">
  <div class="orden">{_esc(job.get("order"))}</div>
  <div class="datos">
    <div class="bloque"><div class="titulo">Cliente:</div><div class="valor">{_esc(job.get("customer"))}</div></div>
    <div class="bloque"><div class="titulo">Producto:</div><div class="valor">{_esc(job.get("product"))}</div></div>
    <div class="bloque"><div class="titulo">Cantidad:</div><div class="valor">{_esc(job.get("quantity"))}</div></div>
  </div>
</div></div></body></html>"""


WORK_ORDER_CSS = """
@page { size: A4; margin: 8mm; }
* { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 0; color: #000; }
.etiqueta { border: 2px solid #000000; padding: 15px; border-radius: 8px; page-break-inside: avoid; page-break-after: always; max-height: 275mm; overflow: hidden; }
.etiqueta:last-child { page-break-after: auto; }
.tabla-header { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
.campo { margin-bottom: 10px; }
.tabla-triple { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
.tabla-triple td { border: none !important; padding: 0 !important; vertical-align: top; }
.lbl { font-size: 10px; font-weight: bold; color: #555555; text-transform: uppercase; margin-bottom: 2px; }
.val { font-size: 20px; font-weight: bold; margin: 0; color: #000000; line-height: 1.1; }
.tabla-unificada { width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 10px; }
.tabla-unificada th, .tabla-unificada td { border: 1px solid #000000; height: 7mm; max-height: 7mm; padding: 0 4px; vertical-align: middle; box-sizing: border-box; }
.tabla-unificada th { font-size: 12px; font-weight: bold; background-color: #f5f5f5; text-align: center; }
.tabla-unificada td.cat-tarjeta { font-size: 11px; font-weight: bold; text-align: center; background-color: #f5f5f5; }
.caja-notas { background-color: #333333; color: #ffffff; padding: 8px 12px; font-size: 13px; font-weight: bold; border-radius: 4px; margin-top: 8px; display: inline-block; }
.img-box { text-align: center; margin-top: 10px; font-size: 0; }
.img-box img { display: inline-block; max-height: 140px; max-width: 48%; margin: 4px; object-fit: contain; vertical-align: top; border: 1px solid #ddd; border-radius: 4px; }
.texto-extra { margin-top: 10px; padding: 10px; font-size: 13px; font-weight: bold; color: #333; border-top: 1px dashed #ccc; text-align: center; white-space: pre-wrap; }
"""

# Mismo criterio que el script: el primer digito que aparece en "Prioridad" manda.
PRIORITY_COLORS = [("1", "#cc0000", "#ffffff"), ("2", "#f1c232", "#000000"), ("3", "#38761d", "#ffffff")]


def _work_order_block(job: Dict[str, Any], pack_qty: str, extra_text: str, images: List[str]) -> str:
    priority = str(job.get("priority") or "")
    base = "padding: 8px 10px;"
    left = base + " font-size: 14px; font-weight: bold; text-align: left;"
    right = base + " font-size: 22px; font-weight: bold; text-align: right;"
    color = next(((bg, fg) for digit, bg, fg in PRIORITY_COLORS if digit in priority), None)
    if color:
        left += f" background-color: {color[0]}; color: {color[1]};"
        right += f" background-color: {color[0]}; color: {color[1]};"
    else:
        left += " color: #444444; border-bottom: 2px solid #000000;"
        right += " color: #000000; border-bottom: 2px solid #000000;"

    # La columna J ("Finalizado") es la que el script imprime como notas.
    notes = str(job.get("finished") or "").strip()
    parts = [
        '<div class="etiqueta">',
        '<table class="tabla-header"><tr>',
        f'<td style="{left}">ETIQUETA DE ENVÍO / PRODUCCIÓN</td>',
        f'<td style="{right}">ORDEN: {_esc(job.get("order"))}</td>',
        "</tr></table>",
        f'<div class="campo"><div class="lbl">CLIENTE:</div><div class="val">{_esc(job.get("customer"))}</div></div>',
        f'<div class="campo"><div class="lbl">PRODUCTO:</div><div class="val">{_esc(job.get("product"))}</div></div>',
        '<table class="tabla-triple"><tr>',
        f'<td style="width: 30%; text-align: left;"><div class="lbl">CANTIDAD:</div><div class="val">{_esc(job.get("quantity"))}</div></td>',
        f'<td style="width: 38%; text-align: center;"><div class="lbl">CANTIDAD POR PACK:</div><div class="val">{_esc(pack_qty or "0")}</div></td>',
        '<td style="width: 32%; text-align: right;"><div class="lbl">FECHA DE ENTREGA:</div>'
        f'<div class="val">{format_due_date(str(job.get("due_date") or ""), str(job.get("due") or ""))}</div></td>',
        "</tr></table>",
        '<table class="tabla-unificada"><thead><tr><th>Etapa</th><th style="width: 35%;">Responsable</th>'
        '<th style="width: 30mm;">Tarjetas</th></tr></thead><tbody>',
        '<tr><td></td><td></td><td class="cat-tarjeta">Laminadas</td></tr>',
        "<tr><td></td><td></td><td></td></tr>",
        '<tr><td></td><td></td><td class="cat-tarjeta">Malas</td></tr>',
        "<tr><td></td><td></td><td></td></tr>",
        '<tr><td></td><td></td><td class="cat-tarjeta">Para completar</td></tr>',
        "<tr><td></td><td></td><td></td></tr>",
        "</tbody></table>",
    ]
    if notes:
        parts.append(f'<div class="caja-notas">{_esc(notes)}</div>')
    if images:
        parts.append('<div class="img-box">' + "".join(f'<img src="{src}" />' for src in images) + "</div>")
    if extra_text.strip():
        parts.append(f'<div class="texto-extra">{_esc(extra_text.strip())}</div>')
    parts.append("</div>")
    return "".join(parts)


def work_order_html(jobs: List[Dict[str, Any]], pack_qty: str = "0", extra_text: str = "",
                    images: Optional[List[str]] = None) -> str:
    blocks = "".join(_work_order_block(job, pack_qty, extra_text, images or []) for job in jobs)
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{WORK_ORDER_CSS}</style></head><body>{blocks}</body></html>'


_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|webp|gif);base64,([A-Za-z0-9+/=\s]+)$")


def validate_images(images: List[str]) -> List[str]:
    """Solo imagenes en data URL (fotos del celular o pegadas): nada de URLs externas."""
    if len(images) > MAX_IMAGES:
        raise ValueError(f"Maximo {MAX_IMAGES} imagenes por orden")
    clean = []
    for src in images:
        match = _DATA_URL_RE.match(src or "")
        if not match:
            raise ValueError("Formato de imagen no valido")
        if len(match.group(2)) * 3 // 4 > MAX_IMAGE_BYTES:
            raise ValueError("Una de las imagenes es demasiado grande")
        clean.append(src)
    return clean


# ----------------------------------------------------------- Rendering ----

def _mm_to_css_px(mm: float) -> float:
    return mm / 25.4 * CSS_DPI


def render_labels_png(html_pages: List[str], size_mm=ORDER_LABEL_MM, dpi: int = LABEL_DPI) -> List[bytes]:
    """Dibuja cada etiqueta a la resolucion de la impresora (1 pixel = 1 punto)."""
    from PIL import Image
    from playwright.sync_api import sync_playwright

    width_dots = round(size_mm[0] / 25.4 * dpi)
    height_dots = round(size_mm[1] / 25.4 * dpi)
    viewport = {"width": round(_mm_to_css_px(size_mm[0])), "height": round(_mm_to_css_px(size_mm[1]))}
    images: List[bytes] = []
    with _render_lock, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport=viewport, device_scale_factor=dpi / CSS_DPI)
            for content in html_pages:
                page.set_content(content, wait_until="load")
                shot = page.screenshot(type="png")
                with Image.open(io.BytesIO(shot)) as img:
                    if img.size != (width_dots, height_dots):
                        img = img.resize((width_dots, height_dots))
                    out = io.BytesIO()
                    img.convert("L").save(out, "PNG")
                    images.append(out.getvalue())
        finally:
            browser.close()
    return images


def render_pdf(content: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with _render_lock, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(content, wait_until="load")
            return page.pdf(prefer_css_page_size=True, print_background=True)
        finally:
            browser.close()


def stack_png(images: List[bytes], gap: int = 12) -> bytes:
    """Vista previa: todas las etiquetas una debajo de otra, con un separador gris."""
    from PIL import Image

    opened = [Image.open(io.BytesIO(data)).convert("RGB") for data in images]
    width = max(img.width for img in opened)
    height = sum(img.height for img in opened) + gap * (len(opened) - 1)
    sheet = Image.new("RGB", (width, height), (200, 200, 200))
    y = 0
    for img in opened:
        sheet.paste(img, (0, y))
        y += img.height + gap
    out = io.BytesIO()
    sheet.save(out, "PNG")
    return out.getvalue()


# ------------------------------------------------------------ Printing ----

def _clamp_copies(copies: Any) -> int:
    try:
        return max(1, min(MAX_COPIES, int(copies)))
    except (TypeError, ValueError):
        return 1


def label_printer(override: str = "") -> str:
    from odoo_integration import odoo_integration

    printer = override.strip() or str(odoo_integration.config.get("default_label_printer", "")).strip()
    if not printer:
        raise ValueError("No hay etiquetadora configurada (Configuracion > Odoo > impresora de etiquetas)")
    return printer


def print_order_labels(jobs: List[Dict[str, Any]], copies: Any = 1, preview: bool = False,
                       printer: str = "") -> Dict[str, Any]:
    from handlers import image_to_zpl_bytes
    from PIL import Image
    from printer import send_raw_to_printer

    pngs = render_labels_png([order_label_html(job) for job in jobs])
    if preview:
        return {"preview": stack_png(pngs), "content_type": "image/png"}

    printer = label_printer(printer)
    safe_copies = _clamp_copies(copies)
    zpl = b"".join(image_to_zpl_bytes(Image.open(io.BytesIO(png))) for png in pngs) * safe_copies
    orders = ", ".join(str(job.get("order")) for job in jobs)
    if not send_raw_to_printer(zpl, printer, job_name=f"Etiqueta orden {orders}"[:120]):
        raise RuntimeError(f"No se pudo enviar a {printer}")
    return {"success": True, "printer": printer, "labels": len(pngs) * safe_copies}


def print_work_orders(jobs: List[Dict[str, Any]], pack_qty: str = "0", extra_text: str = "",
                      images: Optional[List[str]] = None, copies: Any = 1, preview: bool = False,
                      printer: str = "") -> Dict[str, Any]:
    from print_fallbacks import print_order_pdf_with_fallback

    pdf = render_pdf(work_order_html(jobs, pack_qty, extra_text, validate_images(images or [])))
    if preview:
        return {"preview": pdf, "content_type": "application/pdf"}
    orders = "-".join(str(job.get("order")) for job in jobs)
    result = print_order_pdf_with_fallback(envio_id=f"orden-taller-{orders}"[:80], pdf_bytes=pdf,
                                           preferred_printer=printer, copies=_clamp_copies(copies))
    if not result.get("success"):
        raise RuntimeError(result.get("error") or f"No se pudo imprimir en {result.get('printer') or 'la impresora'}")
    return {"success": True, "printer": result.get("printer", ""), "pages": len(jobs)}


def print_preloaded_pdf(pdf: bytes, name: str, target: str = "label", copies: Any = 1,
                        printers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    from print_fallbacks import print_label_pdf_with_fallback, print_order_pdf_with_fallback

    job_name = f"precargada-{re.sub(r'[^A-Za-z0-9_-]+', '_', name)}"[:80]
    printers = printers or {}
    if target == "sheet":
        result = print_order_pdf_with_fallback(envio_id=job_name, pdf_bytes=pdf,
                                               preferred_printer=printers.get("order", ""),
                                               copies=_clamp_copies(copies))
    else:
        # Mismo camino que las etiquetas de Administrado: recorta margenes y manda ZPL.
        result = print_label_pdf_with_fallback(envio_id=job_name, pdf_bytes=pdf,
                                               preferred_printer=printers.get("label", ""),
                                               copies=_clamp_copies(copies))
    if not result.get("success"):
        raise RuntimeError(result.get("error") or f"No se pudo imprimir en {result.get('printer') or 'la impresora'}")
    return {"success": True, "printer": result.get("printer", "")}
