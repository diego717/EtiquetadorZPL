"""Motor de composicion de credenciales basado en objetos libres.

El diseño es un diccionario con dos caras (``front`` y ``back``). Cada cara
tiene un fondo y una lista ordenada de objetos (texto, foto, imagen, QR, codigo
de barras y formas). Las posiciones se expresan como fracciones de la tarjeta y
las medidas tipograficas en puntos, de modo que el mismo diseño se puede
renderizar a 300 o 600 dpi sin cambiar su aspecto.

El modulo no conoce FastAPI: recibe la foto ya recortada, las imagenes de
recursos ya abiertas y una funcion para resolver archivos tipograficos.
"""

from __future__ import annotations

import math
import re
from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

import card_vectors as vectors


MM_PER_INCH = 25.4
POINTS_PER_INCH = 72
FIELD_PATTERN = re.compile(r"\{([^{}\n]{1,80})\}")
BARCODE_SYMBOLOGIES = ("code128", "code39", "ean13", "ean8", "upca", "itf")
SHEET_SIZES_MM = {"A4": (210.0, 297.0), "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6)}
SUPERSAMPLE = 3
ELEMENT_LABELS = {
    "text": "Texto", "photo": "Foto", "image": "Imagen", "qr": "Código QR", "barcode": "Código de barras",
    "rect": "Rectángulo", "ellipse": "Elipse", "line": "Línea", "path": "Trazado",
}

FontResolver = Callable[[str, bool, bool], Optional[Path]]


class BarcodeError(ValueError):
    """El contenido no es valido para la simbologia elegida."""


# --------------------------------------------------------------------------- #
# Datos variables
# --------------------------------------------------------------------------- #

def record_values(metadata: Mapping[str, str], filename: str, sequence: int | None = None) -> dict[str, str]:
    """Campos disponibles para una credencial; las columnas de la planilla mandan."""
    values = {
        "Archivo": Path(filename).stem,
        "Nro": str(sequence) if sequence else "",
        "Fecha": date.today().strftime("%d/%m/%Y"),
        "Año": str(date.today().year),
    }
    values.update({str(key): "" if value is None else str(value) for key, value in metadata.items()})
    return values


def resolve_fields(template: str, values: Mapping[str, str]) -> str:
    return FIELD_PATTERN.sub(lambda match: values.get(match.group(1).strip(), ""), template or "")


def condition_matches(condition: Mapping | None, values: Mapping[str, str]) -> bool:
    if not condition:
        return True
    operator = condition.get("op") or "always"
    if operator == "always":
        return True
    current = values.get(str(condition.get("field") or ""), "").strip().casefold()
    expected = str(condition.get("value") or "").strip().casefold()
    if operator == "equals":
        return current == expected
    if operator == "not_equals":
        return current != expected
    if operator == "contains":
        return expected in current
    if operator == "empty":
        return not current
    if operator == "not_empty":
        return bool(current)
    return True


# --------------------------------------------------------------------------- #
# Utilidades de color, unidades y composicion
# --------------------------------------------------------------------------- #

def card_pixel_size(width_mm: float, height_mm: float, dpi: int) -> tuple[int, int]:
    return max(1, round(width_mm / MM_PER_INCH * dpi)), max(1, round(height_mm / MM_PER_INCH * dpi))


def _rgb(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    clean = str(value).lstrip("#")
    if len(clean) != 6:
        return None
    try:
        return tuple(int(clean[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None


def _rgba(value: str | None, alpha: int = 255) -> tuple[int, int, int, int] | None:
    rgb = _rgb(value)
    return (*rgb, alpha) if rgb else None


def _composite(canvas: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    """Superpone ``layer`` en ``canvas`` aunque quede parcialmente afuera."""
    left, top = max(0, x), max(0, y)
    right, bottom = min(canvas.width, x + layer.width), min(canvas.height, y + layer.height)
    if right <= left or bottom <= top:
        return
    source = layer.crop((left - x, top - y, right - x, bottom - y))
    canvas.alpha_composite(source, (left, top))


def _apply_opacity(layer: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return layer
    alpha = layer.getchannel("A").point(lambda value: round(value * max(0.0, opacity)))
    layer.putalpha(alpha)
    return layer


def _shape_mask(size: tuple[int, int], shape: str, radius: float) -> Image.Image:
    """Mascara suavizada por supermuestreo (PIL no suaviza curvas por si solo)."""
    width, height = size
    big = Image.new("L", (width * SUPERSAMPLE, height * SUPERSAMPLE), 0)
    draw = ImageDraw.Draw(big)
    box = (0, 0, big.width - 1, big.height - 1)
    if shape in {"circle", "ellipse"}:
        draw.ellipse(box, fill=255)
    elif radius > 0:
        draw.rounded_rectangle(box, radius=min(radius * SUPERSAMPLE, min(big.size) / 2), fill=255)
    else:
        draw.rectangle(box, fill=255)
    return big.resize(size, Image.Resampling.LANCZOS)


def _outline_layer(size: tuple[int, int], shape: str, radius: float, color, width: float) -> Image.Image:
    width_px = max(1, round(width * SUPERSAMPLE))
    big = Image.new("RGBA", (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    # PIL dibuja el contorno hacia adentro de la caja, igual que el borde CSS.
    box = (0, 0, big.width - 1, big.height - 1)
    width_px = min(width_px, max(1, min(big.size) // 2))
    if shape in {"circle", "ellipse"}:
        draw.ellipse(box, outline=color, width=width_px)
    elif radius > 0:
        draw.rounded_rectangle(box, radius=min(radius * SUPERSAMPLE, min(big.size) / 2), outline=color, width=width_px)
    else:
        draw.rectangle(box, outline=color, width=width_px)
    return big.resize(size, Image.Resampling.LANCZOS)


def _multiply_mask(mask: Image.Image, alpha: int) -> Image.Image:
    return mask if alpha >= 255 else mask.point(lambda value: value * alpha // 255)


def _colored(mask: Image.Image, color) -> Image.Image:
    layer = Image.new("RGBA", mask.size, (*color[:3], 255))
    layer.putalpha(_multiply_mask(mask, color[3] if len(color) > 3 else 255))
    return layer


def inset_shape_paths(shape: str, size: tuple[float, float], radius: float, stroke_width: float) -> list[dict]:
    """Trazado del contorno de un rectangulo o elipse metido medio grosor hacia adentro."""
    inset = stroke_width / 2
    if shape in {"ellipse", "circle"}:
        return vectors.ellipse_paths(size[0] / 2, size[1] / 2, max(0.25, size[0] / 2 - inset), max(0.25, size[1] / 2 - inset))
    return vectors.rect_paths(inset, inset, size[0] - inset, size[1] - inset, max(0.0, radius - inset))


# --------------------------------------------------------------------------- #
# Tipografia
# --------------------------------------------------------------------------- #

_BUILTIN_FONTS = {
    "sans": {
        (False, False): ("arial.ttf", "DejaVuSans.ttf"),
        (True, False): ("arialbd.ttf", "DejaVuSans-Bold.ttf"),
        (False, True): ("ariali.ttf", "DejaVuSans-Oblique.ttf"),
        (True, True): ("arialbi.ttf", "DejaVuSans-BoldOblique.ttf"),
    },
    "serif": {
        (False, False): ("georgia.ttf", "DejaVuSerif.ttf"),
        (True, False): ("georgiab.ttf", "DejaVuSerif-Bold.ttf"),
        (False, True): ("georgiai.ttf", "DejaVuSerif-Italic.ttf"),
        (True, True): ("georgiaz.ttf", "DejaVuSerif-BoldItalic.ttf"),
    },
    "mono": {
        (False, False): ("consola.ttf", "DejaVuSansMono.ttf"),
        (True, False): ("consolab.ttf", "DejaVuSansMono-Bold.ttf"),
        (False, True): ("consolai.ttf", "DejaVuSansMono-Oblique.ttf"),
        (True, True): ("consolaz.ttf", "DejaVuSansMono-BoldOblique.ttf"),
    },
}


def _builtin_font_path(family: str, bold: bool, italic: bool) -> Path | None:
    names = _BUILTIN_FONTS.get(family, _BUILTIN_FONTS["sans"])[(bold, italic)]
    for candidate in (Path("C:/Windows/Fonts") / names[0], Path("/usr/share/fonts/truetype/dejavu") / names[1]):
        if candidate.exists():
            return candidate
    return None


class FontCache:
    def __init__(self, resolver: FontResolver | None = None) -> None:
        self.resolver = resolver
        self._paths: dict[tuple[str, bool, bool], Path | None] = {}
        self._fonts: dict[tuple[Path | None, int], ImageFont.ImageFont] = {}

    def path(self, family: str, bold: bool, italic: bool) -> Path | None:
        key = (family, bold, italic)
        if key not in self._paths:
            path = self.resolver(family, bold, italic) if self.resolver and family.startswith("system:") else None
            self._paths[key] = path if path and path.is_file() else _builtin_font_path(family, bold, italic)
        return self._paths[key]

    def get(self, family: str, bold: bool, italic: bool, size_px: int) -> ImageFont.ImageFont:
        path = self.path(family, bold, italic)
        size_px = max(1, int(size_px))
        key = (path, size_px)
        if key not in self._fonts:
            try:
                self._fonts[key] = ImageFont.truetype(str(path), size=size_px) if path else ImageFont.load_default(size=size_px)
            except OSError:
                self._fonts[key] = ImageFont.load_default(size=size_px)
        return self._fonts[key]


def _text_width(font: ImageFont.ImageFont, text: str) -> float:
    return font.getlength(text) if text else 0.0


def wrap_lines(text: str, font: ImageFont.ImageFont, max_width: float) -> list[str]:
    """Corte por palabras; las palabras que no entran se parten por caracteres."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if _text_width(font, candidate) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = ""
            while _text_width(font, word) > max_width and len(word) > 1:
                cut = len(word)
                while cut > 1 and _text_width(font, word[:cut]) > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


def layout_text(
    text: str,
    fonts: FontCache,
    *,
    family: str,
    bold: bool,
    italic: bool,
    size_px: float,
    box: tuple[int, int],
    fit: str,
    line_height: float,
) -> tuple[ImageFont.ImageFont, list[str], float]:
    """Devuelve fuente, lineas y alto de linea siguiendo el modo de ajuste."""
    width, height = box
    minimum = max(4.0, size_px * 0.15)
    size = float(size_px)
    while True:
        font = fonts.get(family, bold, italic, round(size))
        lines = wrap_lines(text, font, width) if fit in {"wrap", "wrap_shrink"} else text.split("\n")
        line_px = size * line_height
        fits_width = all(_text_width(font, line) <= width + 0.5 for line in lines)
        fits_height = line_px * len(lines) <= height + 0.5
        if fit in {"none", "wrap"} or size <= minimum:
            return font, lines, line_px
        if fit == "shrink" and fits_width and fits_height:
            return font, lines, line_px
        if fit == "wrap_shrink" and fits_height and fits_width:
            return font, lines, line_px
        size = max(minimum, size * 0.94)


# --------------------------------------------------------------------------- #
# Codigos
# --------------------------------------------------------------------------- #

def qr_matrix(value: str, ecc: str = "M", border: int = 2) -> list[list[bool]]:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q

    levels = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}
    code = qrcode.QRCode(error_correction=levels.get(ecc, ERROR_CORRECT_M), border=border, box_size=1)
    code.add_data(value or " ")
    code.make(fit=True)
    return code.get_matrix()


CODE39_CHARS = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%")
NUMERIC_LENGTHS = {"ean13": (12, 13), "ean8": (7, 8), "upca": (11, 12)}


def validate_barcode_value(symbology: str, value: str) -> None:
    """Mensajes claros antes de llamar a python-barcode."""
    names = {"ean13": "EAN-13", "ean8": "EAN-8", "upca": "UPC-A", "itf": "ITF", "code39": "Code 39", "code128": "Code 128"}
    name = names.get(symbology, symbology)
    if symbology in NUMERIC_LENGTHS or symbology == "itf":
        if not value.isdigit():
            raise BarcodeError(f"{name} sólo admite números y recibió “{value[:30]}”")
    if symbology in NUMERIC_LENGTHS:
        expected = NUMERIC_LENGTHS[symbology]
        if len(value) not in expected:
            raise BarcodeError(f"{name} necesita {expected[0]} dígitos (o {expected[1]} con verificador) y tiene {len(value)}")
    if symbology == "itf" and len(value) % 2:
        raise BarcodeError("ITF necesita una cantidad par de dígitos")
    if symbology == "code39" and set(value.upper()) - CODE39_CHARS:
        raise BarcodeError("Code 39 sólo admite mayúsculas, números y - . $ / + % espacio")
    if symbology == "code128" and any(ord(char) > 127 for char in value):
        raise BarcodeError("Code 128 no admite letras acentuadas ni ñ")


def barcode_modules(symbology: str, value: str) -> tuple[str, str]:
    """Devuelve la secuencia de modulos ('1' barra, '0' espacio) y el texto legible."""
    if symbology not in BARCODE_SYMBOLOGIES:
        raise BarcodeError("tipo de código no admitido")
    value = (value or "").strip()
    if not value:
        raise BarcodeError("está vacío")
    validate_barcode_value(symbology, value)
    try:
        import barcode
    except ImportError as exc:  # pragma: no cover - dependencia opcional
        raise BarcodeError("Falta instalar python-barcode") from exc
    options = {"add_checksum": False} if symbology == "code39" else {}
    try:
        code = barcode.get(symbology, value, options=options) if options else barcode.get(symbology, value)
        modules = "".join(code.build())
        readable = code.get_fullcode()
    except Exception as exc:  # python-barcode usa varias excepciones propias
        raise BarcodeError("el contenido no es válido para este tipo de código") from exc
    if not modules or set(modules) - {"0", "1"}:
        raise BarcodeError("No se pudo generar el codigo")
    return modules, str(readable)


def _bar_runs(modules: str) -> Iterable[tuple[int, int]]:
    start = None
    for index, module in enumerate(modules + "0"):
        if module == "1" and start is None:
            start = index
        elif module != "1" and start is not None:
            yield start, index - start
            start = None


def qr_svg(value: str, ecc: str, color: str, background: str | None) -> str:
    matrix = qr_matrix(value, ecc)
    size = len(matrix)
    path = "".join(f"M{x},{y}h1v1h-1z" for y, row in enumerate(matrix) for x, cell in enumerate(row) if cell)
    back = f'<rect width="{size}" height="{size}" fill="{escape(background)}"/>' if background else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" shape-rendering="crispEdges">'
        f'{back}<path d="{path}" fill="{escape(color)}"/></svg>'
    )


def barcode_svg(symbology: str, value: str, show_text: bool, color: str, background: str | None) -> str:
    modules, readable = barcode_modules(symbology, value)
    count = len(modules)
    height = max(20, round(count * 0.32))
    text_height = round(height * 0.22) if show_text else 0
    bars = "".join(f'<rect x="{start}" y="0" width="{length}" height="{height - text_height}"/>' for start, length in _bar_runs(modules))
    back = f'<rect width="{count}" height="{height}" fill="{escape(background)}"/>' if background else ""
    label = (
        f'<text x="{count / 2}" y="{height - 1}" text-anchor="middle" font-family="Arial, sans-serif" '
        f'font-size="{text_height * 0.9:.2f}" fill="{escape(color)}">{escape(readable)}</text>'
        if show_text else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {count} {height}" preserveAspectRatio="none" '
        f'shape-rendering="crispEdges">{back}<g fill="{escape(color)}">{bars}</g>{label}</svg>'
    )


# --------------------------------------------------------------------------- #
# Render de objetos
# --------------------------------------------------------------------------- #

class CardRenderer:
    def __init__(
        self,
        *,
        width_mm: float,
        height_mm: float,
        dpi: int,
        fonts: FontCache | None = None,
        assets: Mapping[str, Image.Image] | None = None,
    ) -> None:
        self.width_mm = width_mm
        self.height_mm = height_mm
        self.dpi = dpi
        self.size = card_pixel_size(width_mm, height_mm, dpi)
        self.fonts = fonts or FontCache()
        self.assets = assets or {}

    def pt(self, points: float) -> float:
        return float(points or 0) * self.dpi / POINTS_PER_INCH

    def render_side(
        self,
        side: Mapping,
        values: Mapping[str, str],
        portrait: Image.Image | None,
    ) -> Image.Image:
        background = _rgb(side.get("background_color")) or (255, 255, 255)
        card = Image.new("RGBA", self.size, (*background, 255))
        image_id = side.get("background_image")
        if image_id and image_id in self.assets:
            card.alpha_composite(vectors.fit_asset(self.assets[image_id], self.size, "cover"))
        for element in side.get("elements") or []:
            if element.get("hidden") or not condition_matches(element.get("condition"), values):
                continue
            self._render_element(card, element, values, portrait)
        return card.convert("RGB")

    def inspect_side(self, side: Mapping, values: Mapping[str, str]) -> list[dict]:
        """Revisa una cara sin componerla: datos faltantes, textos achicados o cortados y códigos inválidos."""
        issues: list[dict] = []

        def report(level: str, element: Mapping, message: str) -> None:
            label = str(element.get("name") or ELEMENT_LABELS.get(str(element.get("type")), "Objeto"))
            issues.append({"level": level, "element": label, "message": message})

        for element in side.get("elements") or []:
            if element.get("hidden") or not condition_matches(element.get("condition"), values):
                continue
            kind = element.get("type")
            template = str(element.get("text") if kind == "text" else element.get("value") or "")
            if kind in {"text", "qr", "barcode"}:
                missing = [name.strip() for name in FIELD_PATTERN.findall(template) if not values.get(name.strip(), "").strip()]
                if missing:
                    report("warning", element, "sin dato en " + ", ".join(f"{{{name}}}" for name in dict.fromkeys(missing)))
            width = max(1, round(float(element.get("w", 0.1)) * self.size[0]))
            height = max(1, round(float(element.get("h", 0.1)) * self.size[1]))
            if kind == "text":
                text = resolve_fields(template, values)
                if element.get("uppercase"):
                    text = text.upper()
                if not text.strip():
                    continue
                padding = self.pt(element.get("padding", 0))
                inner = (max(1, width - padding * 2), max(1, height - padding * 2))
                requested = self.pt(element.get("size", 12))
                fit = str(element.get("fit") or "shrink")
                font, lines, line_px = layout_text(
                    text, self.fonts, family=str(element.get("font") or "sans"), bold=bool(element.get("bold")),
                    italic=bool(element.get("italic")), size_px=requested, box=inner, fit=fit,
                    line_height=float(element.get("line_height") or 1.15),
                )
                overflow = any(_text_width(font, line) > inner[0] + 0.5 for line in lines) or line_px * len(lines) > inner[1] + 0.5
                ratio = font.size / max(1.0, requested)
                if overflow:
                    report("error", element, "el texto no entra completo y se corta")
                elif ratio < 0.7:
                    report("warning", element, f"el texto se achicó al {round(ratio * 100)} % para entrar")
            elif kind == "barcode":
                value = resolve_fields(template, values).strip()
                if not value:
                    continue
                try:
                    modules, _readable = barcode_modules(str(element.get("symbology") or "code128"), value)
                except BarcodeError as exc:
                    report("error", element, f"código inválido ({exc})")
                    continue
                if width / len(modules) < 2:
                    report("warning", element, "barras muy finas: puede no leerse, agrandá el objeto")
            elif kind == "qr":
                value = resolve_fields(template, values).strip()
                if value and min(width, height) / len(qr_matrix(value, str(element.get("ecc") or "M"))) < 3:
                    report("warning", element, "QR muy denso para su tamaño: puede no leerse")
            elif kind == "image" and str(element.get("asset") or "") not in self.assets:
                report("warning", element, "la imagen no está cargada")
        return issues

    def _render_element(self, card: Image.Image, element: Mapping, values: Mapping[str, str], portrait: Image.Image | None) -> None:
        placed = self.element_layer(element, values, portrait)
        if placed is not None:
            layer, left, top = placed
            _composite(card, layer, left, top)

    def element_layer(self, element: Mapping, values: Mapping[str, str], portrait: Image.Image | None) -> tuple[Image.Image, int, int] | None:
        """Capa RGBA del objeto ya girada y su posicion en la tarjeta (pixeles)."""
        width = max(1, round(float(element.get("w", 0.1)) * self.size[0]))
        height = max(1, round(float(element.get("h", 0.1)) * self.size[1]))
        kind = element.get("type")
        painter = {
            "text": self._text_layer,
            "photo": self._photo_layer,
            "image": self._image_layer,
            "qr": self._qr_layer,
            "barcode": self._barcode_layer,
            "rect": self._shape_layer,
            "ellipse": self._shape_layer,
            "line": self._line_layer,
            "path": self._path_layer,
        }.get(kind)
        if painter is None:
            return None
        layer = painter(element, (width, height), values, portrait)
        if layer is None:
            return None
        layer = _apply_opacity(layer, float(element.get("opacity", 1)))
        center_x = (float(element.get("x", 0)) + float(element.get("w", 0)) / 2) * self.size[0]
        center_y = (float(element.get("y", 0)) + float(element.get("h", 0)) / 2) * self.size[1]
        rotation = float(element.get("rotation") or 0) % 360
        if rotation:
            layer = layer.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
        return layer, round(center_x - layer.width / 2), round(center_y - layer.height / 2)

    def text_lines(self, element, size, values) -> tuple[ImageFont.ImageFont, list[tuple[str, float, float, float]]] | None:
        """Ubicacion de cada linea del texto en la caja: (linea, x, y del medio, ancho)."""
        text = resolve_fields(str(element.get("text") or ""), values)
        if element.get("uppercase"):
            text = text.upper()
        if not text.strip():
            return None
        padding = self.pt(element.get("padding", 0))
        inner = (max(1, size[0] - padding * 2), max(1, size[1] - padding * 2))
        font, lines, line_px = layout_text(
            text,
            self.fonts,
            family=str(element.get("font") or "sans"),
            bold=bool(element.get("bold")),
            italic=bool(element.get("italic")),
            size_px=self.pt(element.get("size", 12)),
            box=inner,
            fit=str(element.get("fit") or "shrink"),
            line_height=float(element.get("line_height") or 1.15),
        )
        total = line_px * len(lines)
        valign = element.get("valign") or "middle"
        top = padding + (0 if valign == "top" else inner[1] - total if valign == "bottom" else (inner[1] - total) / 2)
        align = element.get("align") or "left"
        placed = []
        for index, line in enumerate(lines):
            line_width = _text_width(font, line)
            if align == "center":
                x = padding + (inner[0] - line_width) / 2
            elif align == "right":
                x = padding + inner[0] - line_width
            else:
                x = padding
            placed.append((line, x, top + line_px * index + line_px / 2, line_width))
        return font, placed

    @staticmethod
    def underline_box(font, x: float, y: float, width: float) -> tuple[float, float, float, float]:
        ascent, descent = font.getmetrics()
        underline_y = y + (ascent - descent) / 2 + max(1, font.size * 0.08)
        thickness = max(1, round(font.size * 0.06))
        return x, underline_y - thickness / 2, x + width, underline_y + thickness / 2

    def _text_layer(self, element, size, values, _portrait):
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        fill = _rgba(element.get("fill"))
        if fill:
            mask = _shape_mask(size, "rect", self.pt(element.get("radius", 0)))
            layer.paste(Image.new("RGBA", size, fill), (0, 0), mask)
        placement = self.text_lines(element, size, values)
        if placement is None:
            return layer if fill else None
        font, lines = placement
        draw = ImageDraw.Draw(layer)
        color = _rgba(element.get("color")) or (23, 32, 43, 255)
        stroke_width = round(self.pt(element.get("stroke_width", 0))) if element.get("stroke_color") else 0
        stroke_fill = _rgba(element.get("stroke_color")) if stroke_width else None
        for line, x, y, line_width in lines:
            draw.text((x, y), line, font=font, fill=color, anchor="lm", stroke_width=stroke_width, stroke_fill=stroke_fill)
            if element.get("underline") and line:
                left, top, right, bottom = self.underline_box(font, x, y, line_width)
                center = (top + bottom) / 2
                draw.line((left, center, right, center), fill=color, width=max(1, round(bottom - top)))
        return layer

    def _fit_image(self, source, size: tuple[int, int], mode: str) -> Image.Image:
        return vectors.fit_asset(source, size, mode)

    def _masked(self, layer: Image.Image, element, shape: str) -> Image.Image:
        radius = self.pt(element.get("radius", 0))
        mask = _shape_mask(layer.size, shape, radius)
        alpha = Image.composite(layer.getchannel("A"), Image.new("L", layer.size, 0), mask)
        layer.putalpha(alpha)
        stroke = _rgba(element.get("stroke_color"))
        stroke_width = self.pt(element.get("stroke_width", 0))
        if stroke and stroke_width > 0:
            layer.alpha_composite(_outline_layer(layer.size, shape, radius, stroke, stroke_width))
        return layer

    def _photo_layer(self, element, size, _values, portrait):
        if portrait is None:
            return None
        source = portrait.convert("L").convert("RGB") if element.get("grayscale") else portrait
        layer = self._fit_image(source, size, str(element.get("image_fit") or "cover"))
        shape = str(element.get("shape") or "rect")
        return self._masked(layer, element, "circle" if shape == "circle" else "rect")

    def _image_layer(self, element, size, _values, _portrait):
        asset = self.assets.get(str(element.get("asset") or ""))
        if asset is None:
            return None
        layer = self._fit_image(asset, size, str(element.get("image_fit") or "contain"))
        recolor = _rgb(element.get("recolor"))
        if recolor:
            # Logo de un solo color (por ejemplo blanco sobre una banda): se conserva la transparencia.
            alpha = layer.getchannel("A")
            layer = Image.new("RGBA", layer.size, (*recolor, 255))
            layer.putalpha(alpha)
        elif element.get("grayscale"):
            alpha = layer.getchannel("A")
            layer = layer.convert("L").convert("RGBA")
            layer.putalpha(alpha)
        return self._masked(layer, element, "rect")

    def _qr_layer(self, element, size, values, _portrait):
        value = resolve_fields(str(element.get("value") or ""), values).strip()
        if not value:
            return None
        matrix = qr_matrix(value, str(element.get("ecc") or "M"))
        modules = len(matrix)
        side = min(size)
        module_px = max(1, side // modules)
        code_px = module_px * modules
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        background = _rgba(element.get("background"))
        offset = ((size[0] - code_px) // 2, (size[1] - code_px) // 2)
        if background:
            ImageDraw.Draw(layer).rectangle((offset[0], offset[1], offset[0] + code_px - 1, offset[1] + code_px - 1), fill=background)
        draw = ImageDraw.Draw(layer)
        color = _rgba(element.get("color")) or (0, 0, 0, 255)
        for row_index, row in enumerate(matrix):
            for column_index, cell in enumerate(row):
                if cell:
                    x = offset[0] + column_index * module_px
                    y = offset[1] + row_index * module_px
                    draw.rectangle((x, y, x + module_px - 1, y + module_px - 1), fill=color)
        return layer

    def _barcode_layer(self, element, size, values, _portrait):
        value = resolve_fields(str(element.get("value") or ""), values).strip()
        if not value:
            return None
        try:
            modules, readable = barcode_modules(str(element.get("symbology") or "code128"), value)
        except BarcodeError:
            return self._error_layer(size, "Código inválido")
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        background = _rgba(element.get("background"))
        if background:
            layer.paste(Image.new("RGBA", size, background))
        draw = ImageDraw.Draw(layer)
        color = _rgba(element.get("color")) or (0, 0, 0, 255)
        show_text = bool(element.get("show_text", True))
        text_height = round(size[1] * 0.22) if show_text else 0
        bar_height = max(1, size[1] - text_height)
        count = len(modules)
        module_px = size[0] / count
        if module_px >= 1:
            # Modulos enteros: barras parejas para que la impresora no las deforme.
            module_px = math.floor(module_px)
        start_x = (size[0] - module_px * count) / 2
        for start, length in _bar_runs(modules):
            left = round(start_x + start * module_px)
            right = round(start_x + (start + length) * module_px) - 1
            draw.rectangle((left, 0, max(left, right), bar_height - 1), fill=color)
        if show_text:
            font = self.fonts.get("sans", False, False, max(6, round(text_height * 0.9)))
            draw.text((size[0] / 2, bar_height + text_height / 2), readable, font=font, fill=color, anchor="mm")
        return layer

    def _shape_layer(self, element, size, _values, _portrait):
        shape = "ellipse" if element.get("type") == "ellipse" else "rect"
        radius = self.pt(element.get("radius", 0)) if shape == "rect" else 0
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        paint = vectors.paint_image(size, element.get("gradient"), element.get("fill"))
        if paint is not None:
            layer.paste(paint, (0, 0), _shape_mask(size, shape, radius))
        stroke = _rgba(element.get("stroke_color"))
        stroke_width = self.pt(element.get("stroke_width", 0))
        if stroke and stroke_width > 0:
            if str(element.get("dash") or "solid") == "solid":
                layer.alpha_composite(_outline_layer(size, shape, radius, stroke, stroke_width))
            else:
                # Contorno punteado: el trazo va por dentro de la caja, igual que el liso.
                mask = self._stroke_mask(inset_shape_paths(shape, size, radius, stroke_width), size, (0, 0), stroke_width, element)
                if mask is not None:
                    layer.alpha_composite(_colored(mask, stroke))
        return layer

    def _stroke_mask(self, paths, size, offset, width, element) -> Image.Image | None:
        flat = [(subpath["closed"], [(x + offset[0], y + offset[1]) for x, y in vectors.flatten(subpath, 0.15)]) for subpath in paths]
        geometry = vectors.stroke_geometry(
            flat, width, cap=str(element.get("line_cap") or "butt"), join=str(element.get("line_join") or "miter"),
            dash=str(element.get("dash") or "solid"),
        )
        if geometry is None:
            return None
        return vectors.fill_mask(vectors.geometry_rings(geometry), size, "evenodd")

    def _vector_layer(self, element, size, paths, *, fill: bool, stroke_px: float | None = None) -> Image.Image | None:
        """Relleno y contorno centrado de trazados en pixeles locales; la capa crece si el trazo sobresale."""
        stroke = _rgba(element.get("stroke_color"))
        stroke_width = (stroke_px if stroke_px is not None else self.pt(element.get("stroke_width", 0))) if stroke else 0
        bounds = vectors.paths_bounds(paths, 0.5) or (0, 0, size[0], size[1])
        reach = stroke_width / 2 * (vectors.MITER_LIMIT if str(element.get("line_join") or "miter") == "miter" else 1.5) + 2 if stroke_width else 1
        pad = math.ceil(max(0, -bounds[0], -bounds[1], bounds[2] - size[0], bounds[3] - size[1]) + reach)
        padded = (size[0] + pad * 2, size[1] + pad * 2)
        layer = Image.new("RGBA", padded, (0, 0, 0, 0))
        if fill:
            paint = vectors.paint_image(padded, element.get("gradient"), element.get("fill"), (pad, pad, size[0], size[1]))
            if paint is not None:
                rings = [[(x + pad, y + pad) for x, y in vectors.flatten(subpath, 0.15)] for subpath in paths]
                layer.paste(paint, (0, 0), vectors.fill_mask(rings, padded, str(element.get("fill_rule") or "evenodd")))
        if stroke and stroke_width > 0:
            mask = self._stroke_mask(paths, padded, (pad, pad), stroke_width, element)
            if mask is not None:
                layer.alpha_composite(_colored(mask, stroke))
        return layer

    def _path_layer(self, element, size, _values, _portrait):
        paths = vectors.scale_paths(vectors.normalize_paths(element.get("paths")), size[0], size[1])
        if not paths:
            return None
        return self._vector_layer(element, size, paths, fill=True)

    def _line_layer(self, element, size, _values, _portrait):
        line = {**element, "stroke_color": element.get("stroke_color") or "#17202b"}
        paths = [{"closed": False, "nodes": [vectors.node((0, size[1] / 2)), vectors.node((size[0], size[1] / 2))]}]
        return self._vector_layer(line, size, paths, fill=False, stroke_px=max(1.0, self.pt(element.get("stroke_width", 1) or 1)))

    def _error_layer(self, size, message: str) -> Image.Image:
        layer = Image.new("RGBA", size, (255, 235, 235, 255))
        draw = ImageDraw.Draw(layer)
        font = self.fonts.get("sans", True, False, max(6, min(size[1] // 3, size[0] // max(1, len(message)) * 2)))
        draw.text((size[0] / 2, size[1] / 2), message, font=font, fill=(180, 35, 35, 255), anchor="mm")
        return layer


# --------------------------------------------------------------------------- #
# Salida PDF
# --------------------------------------------------------------------------- #

def _jpeg_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.convert("RGB").save(output, "JPEG", quality=95, subsampling=0, dpi=(300, 300))
    return output.getvalue()


def sheet_grid(card_mm: tuple[float, float], page_mm: tuple[float, float], margin_mm: float, gap_mm: float) -> tuple[int, int, bool]:
    """Columnas, filas y si conviene girar la hoja para que entren mas tarjetas."""
    def fit(page):
        usable_w = page[0] - margin_mm * 2 + gap_mm
        usable_h = page[1] - margin_mm * 2 + gap_mm
        return max(0, math.floor(usable_w / (card_mm[0] + gap_mm))), max(0, math.floor(usable_h / (card_mm[1] + gap_mm)))
    portrait = fit(page_mm)
    landscape = fit((page_mm[1], page_mm[0]))
    if landscape[0] * landscape[1] > portrait[0] * portrait[1]:
        return landscape[0], landscape[1], True
    return portrait[0], portrait[1], False


def _place_face(page, rect, face) -> None:
    """Inserta una cara: imagen compuesta o documento vectorial de una pagina."""
    if isinstance(face, Image.Image):
        page.insert_image(rect, stream=_jpeg_bytes(face))
    else:
        page.show_pdf_page(rect, face, 0)


def build_pdf(
    pages: list[list],
    card_mm: tuple[float, float],
    *,
    layout: str = "card",
    sheet: str = "A4",
    margin_mm: float = 10,
    gap_mm: float = 4,
    crop_marks: bool = True,
    duplex_mirror: bool = True,
) -> bytes:
    """Arma el PDF.

    ``pages`` es una lista de credenciales; cada credencial es la lista de sus
    caras a imprimir (frente y, opcionalmente, dorso). Cada cara es una imagen
    o un documento PDF vectorial de una pagina.
    """
    import fitz

    to_pt = lambda millimeters: millimeters / MM_PER_INCH * POINTS_PER_INCH  # noqa: E731
    document = fitz.open()
    card_w, card_h = to_pt(card_mm[0]), to_pt(card_mm[1])
    if layout != "sheet":
        for faces in pages:
            for face in faces:
                page = document.new_page(width=card_w, height=card_h)
                _place_face(page, page.rect, face)
        return document.tobytes(garbage=3, deflate=True)

    page_mm = SHEET_SIZES_MM.get(sheet.upper(), SHEET_SIZES_MM["A4"])
    columns, rows, rotate = sheet_grid(card_mm, page_mm, margin_mm, gap_mm)
    if columns < 1 or rows < 1:
        raise ValueError("La credencial no entra en la hoja con esos márgenes")
    if rotate:
        page_mm = (page_mm[1], page_mm[0])
    page_w, page_h = to_pt(page_mm[0]), to_pt(page_mm[1])
    gap = to_pt(gap_mm)
    grid_w = columns * card_w + (columns - 1) * gap
    grid_h = rows * card_h + (rows - 1) * gap
    origin_x = (page_w - grid_w) / 2
    origin_y = (page_h - grid_h) / 2
    per_sheet = columns * rows
    face_count = max((len(faces) for faces in pages), default=1)

    def draw_marks(page) -> None:
        mark, offset = to_pt(4), to_pt(1)
        shape = page.new_shape()
        xs = sorted({origin_x + column * (card_w + gap) for column in range(columns)} | {origin_x + column * (card_w + gap) + card_w for column in range(columns)})
        ys = sorted({origin_y + row * (card_h + gap) for row in range(rows)} | {origin_y + row * (card_h + gap) + card_h for row in range(rows)})
        for x in xs:
            shape.draw_line((x, origin_y - offset - mark), (x, origin_y - offset))
            shape.draw_line((x, origin_y + grid_h + offset), (x, origin_y + grid_h + offset + mark))
        for y in ys:
            shape.draw_line((origin_x - offset - mark, y), (origin_x - offset, y))
            shape.draw_line((origin_x + grid_w + offset, y), (origin_x + grid_w + offset + mark, y))
        shape.finish(color=(0, 0, 0), width=0.4)
        shape.commit()

    for first in range(0, len(pages), per_sheet):
        batch = pages[first:first + per_sheet]
        for face_index in range(face_count):
            page = document.new_page(width=page_w, height=page_h)
            for slot, faces in enumerate(batch):
                if face_index >= len(faces):
                    continue
                row, column = divmod(slot, columns)
                if face_index == 1 and duplex_mirror:
                    column = columns - 1 - column
                x = origin_x + column * (card_w + gap)
                y = origin_y + row * (card_h + gap)
                _place_face(page, fitz.Rect(x, y, x + card_w, y + card_h), faces[face_index])
            if crop_marks:
                draw_marks(page)
    return document.tobytes(garbage=3, deflate=True)
