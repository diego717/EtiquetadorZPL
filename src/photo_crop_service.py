"""Procesamiento de imagen reutilizable por el recortador web.

El modulo no conoce FastAPI ni interfaces graficas. Trabaja siempre sobre la
imagen original orientada mediante EXIF para que la vista previa y la
exportacion compartan el mismo sistema de coordenadas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
EXPORT_FORMATS = {
    "JPG": (".jpg", "JPEG"),
    "PNG": (".png", "PNG"),
    "WEBP": (".webp", "WEBP"),
}


@dataclass(frozen=True)
class ExportTransform:
    crop: tuple[float, float, float, float]
    brightness: float = 1.0
    contrast: float = 1.0
    rotation: int = 0


def open_oriented_image(path: Path) -> Image.Image:
    with Image.open(path) as source:
        return ImageOps.exif_transpose(source).convert("RGB").copy()


def default_crop(image_size: tuple[int, int], ratio: float) -> tuple[float, float, float, float]:
    width, height = image_size
    if width / height > ratio:
        crop_h = float(height)
        crop_w = crop_h * ratio
    else:
        crop_w = float(width)
        crop_h = crop_w / ratio
    left = (width - crop_w) / 2
    top = (height - crop_h) / 2
    return left, top, left + crop_w, top + crop_h


def compute_face_crop(
    image_size: tuple[int, int],
    face_box: tuple[int, int, int, int],
    eye_line: Optional[float],
    hair_margin: float,
    ratio: float,
    eye_position: float,
    face_fill: Optional[float] = None,
) -> tuple[float, float, float, float]:
    """Calcula el encuadre de credencial usado por las interfaces web y desktop.

    ``face_fill`` es la fracción del alto del recorte que ocupa el rostro
    detectado; si no se indica se deriva del margen para el pelo.
    """
    x, y, width, height = (float(value) for value in face_box)
    image_w, image_h = image_size
    maximum_h = min(image_h, image_w / ratio)
    if face_fill is None:
        face_fill = max(0.50, min(0.68, 0.72 - hair_margin * 0.55))
        width_fill = 0.68
    else:
        face_fill = max(0.25, min(0.90, face_fill))
        width_fill = max(0.68, face_fill)
    crop_h = min(maximum_h, max(height / face_fill, width / (ratio * width_fill)))
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
    return left, top, left + crop_w, top + crop_h


def quality_issues(image: Image.Image, face_box: Optional[tuple[int, int, int, int]]) -> list[str]:
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    issues: list[str] = []
    if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < 45:
        issues.append("Posible desenfoque")
    brightness = float(gray.mean())
    contrast = float(gray.std())
    if brightness < 62:
        issues.append("Foto muy oscura")
    elif brightness > 205:
        issues.append("Foto muy clara")
    if contrast < 22:
        issues.append("Contraste bajo")
    if face_box is None:
        issues.append("Rostro no detectado")
    elif face_box[3] < image.height * 0.12:
        issues.append("Rostro pequeño")
    return issues


def render_export(
    image: Image.Image,
    transform: ExportTransform,
    output_size: tuple[int, int] | None,
) -> Image.Image:
    rotation = int(transform.rotation) % 360
    if rotation not in {0, 90, 180, 270}:
        raise ValueError("La rotacion debe ser 0, 90, 180 o 270 grados")
    working = image.rotate(-rotation, expand=True) if rotation else image.copy()
    working = ImageEnhance.Brightness(working).enhance(max(0.5, min(1.5, transform.brightness)))
    working = ImageEnhance.Contrast(working).enhance(max(0.5, min(1.5, transform.contrast)))
    left, top, right, bottom = transform.crop
    left = max(0, min(working.width - 1, round(left)))
    top = max(0, min(working.height - 1, round(top)))
    right = max(left + 1, min(working.width, round(right)))
    bottom = max(top + 1, min(working.height, round(bottom)))
    result = working.crop((left, top, right, bottom))
    if output_size:
        result = result.resize(output_size, Image.Resampling.LANCZOS)
    return result


def encode_image(image: Image.Image, format_name: str) -> tuple[bytes, str, str]:
    normalized = format_name.upper()
    if normalized not in EXPORT_FORMATS:
        raise ValueError("Formato de salida no admitido")
    extension, pil_format = EXPORT_FORMATS[normalized]
    output = BytesIO()
    if pil_format == "JPEG":
        image.convert("RGB").save(output, pil_format, quality=92, optimize=True)
    elif pil_format == "PNG":
        image.save(output, pil_format, optimize=True)
    else:
        image.save(output, pil_format, quality=92, method=4)
    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[pil_format]
    return output.getvalue(), extension, mime


def safe_output_stem(filename: str, suffix: str = "") -> str:
    stem = Path(filename).stem
    suffix = re.sub(r'[^\w .-]+', "_", suffix, flags=re.UNICODE)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", f"{stem}{suffix}").strip(". ")
    return value[:180] or "foto"


def process_background(image: Image.Image, mode: str = "original", strength: int = 55) -> Image.Image:
    """Suaviza o aclara el fondo conservando el sujeto central.

    GrabCut se ejecuta sobre una copia reducida para mantener tiempos razonables
    en lotes grandes. Ante cualquier fallo devuelve la imagen sin modificar.
    """
    normalized = mode.casefold()
    if normalized == "original":
        return image.copy()
    if normalized not in {"blur", "light"}:
        raise ValueError("Modo de fondo no admitido")
    amount = max(0, min(100, int(strength))) / 100
    if amount <= 0:
        return image.copy()

    source = image.convert("RGB")
    work = source.copy()
    work.thumbnail((900, 900), Image.Resampling.LANCZOS)
    array = cv2.cvtColor(np.asarray(work), cv2.COLOR_RGB2BGR)
    height, width = array.shape[:2]
    margin_x = max(2, round(width * 0.035))
    margin_y = max(2, round(height * 0.025))
    rectangle = (margin_x, margin_y, max(1, width - margin_x * 2), max(1, height - margin_y * 2))
    mask = np.zeros((height, width), np.uint8)
    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(array, mask, rectangle, background_model, foreground_model, 4, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return source.copy()
    foreground = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
    mask_image = Image.fromarray(foreground).resize(source.size, Image.Resampling.LANCZOS)
    blur_radius = max(2, round(min(source.size) * 0.012))
    mask_image = mask_image.filter(ImageFilter.GaussianBlur(blur_radius))
    if normalized == "blur":
        effect = source.filter(ImageFilter.GaussianBlur(max(4, round(min(source.size) * 0.055))))
    else:
        effect = Image.new("RGB", source.size, (245, 247, 250))
    background = Image.blend(source, effect, amount)
    return Image.composite(source, background, mask_image)


def _font(size: int, bold: bool = False, family: str = "sans", font_path: Path | None = None) -> ImageFont.ImageFont:
    if font_path and font_path.is_file():
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except OSError:
            pass
    windows = {
        "sans": ("arialbd.ttf", "arial.ttf"),
        "serif": ("georgiab.ttf", "georgia.ttf"),
        "mono": ("consolab.ttf", "consola.ttf"),
    }
    linux = {
        "sans": ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"),
        "serif": ("DejaVuSerif-Bold.ttf", "DejaVuSerif.ttf"),
        "mono": ("DejaVuSansMono-Bold.ttf", "DejaVuSansMono.ttf"),
    }
    family = family if family in windows else "sans"
    candidates = [
        Path("C:/Windows/Fonts") / windows[family][0 if bold else 1],
        Path("/usr/share/fonts/truetype/dejavu") / linux[family][0 if bold else 1],
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    bold: bool = False,
    family: str = "sans",
    font_path: Path | None = None,
) -> ImageFont.ImageFont:
    size = start_size
    while size > 18:
        font = _font(size, bold, family, font_path)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return _font(size, bold, family, font_path)


def _draw_aligned_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int] | str,
    alignment: str,
) -> None:
    text_box = draw.textbbox((0, 0), text, font=font)
    text_width = text_box[2] - text_box[0]
    if alignment == "right":
        x = box[2] - text_width
    elif alignment == "center":
        x = box[0] + (box[2] - box[0] - text_width) / 2
    else:
        x = box[0]
    draw.text((round(x), box[1]), text, fill=fill, font=font)


def _hex_color(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    try:
        clean = value.lstrip("#")
        if len(clean) != 6:
            return fallback
        return tuple(int(clean[index:index + 2], 16) for index in (0, 2, 4))
    except (ValueError, TypeError):
        return fallback


def _card_positions(template: str, orientation: str) -> dict[str, tuple[float, float, float, float]]:
    if orientation == "portrait":
        return {
            "title": (0.07, 0.045, 0.67, 0.08), "logo": (0.77, 0.035, 0.17, 0.10),
            "photo": (0.18, 0.17, 0.64, 0.42), "name": (0.08, 0.64, 0.84, 0.09),
            "role": (0.08, 0.74, 0.84, 0.055), "qr": (0.64, 0.81, 0.27, 0.16),
        }
    layouts = {
        "classic": {
            "title": (0.04, 0.05, 0.70, 0.10), "logo": (0.78, 0.035, 0.17, 0.13),
            "photo": (0.04, 0.26, 0.31, 0.68), "name": (0.39, 0.30, 0.55, 0.13),
            "role": (0.39, 0.44, 0.55, 0.08), "qr": (0.74, 0.60, 0.20, 0.31),
        },
        "sidebar": {
            "title": (0.38, 0.08, 0.56, 0.10), "logo": (0.07, 0.055, 0.21, 0.12),
            "photo": (0.05, 0.25, 0.25, 0.62), "name": (0.38, 0.31, 0.55, 0.13),
            "role": (0.38, 0.46, 0.55, 0.08), "qr": (0.72, 0.62, 0.21, 0.31),
        },
        "minimal": {
            "title": (0.39, 0.10, 0.48, 0.08), "logo": (0.82, 0.055, 0.13, 0.11),
            "photo": (0.05, 0.12, 0.29, 0.76), "name": (0.39, 0.33, 0.55, 0.13),
            "role": (0.39, 0.48, 0.55, 0.08), "qr": (0.77, 0.63, 0.17, 0.27),
        },
    }
    return layouts.get(template, layouts["classic"])


def _pixel_box(box: tuple[float, float, float, float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    x, y, width, height = box
    return round(x * size[0]), round(y * size[1]), round((x + width) * size[0]), round((y + height) * size[1])


def render_card(
    portrait: Image.Image,
    *,
    title: str,
    color: str,
    name: str,
    role: str,
    qr_value: str,
    logo: Image.Image | None = None,
    background: Image.Image | None = None,
    background_color: str = "#f9fafc",
    text_color: str = "#17202b",
    template: str = "classic",
    orientation: str = "landscape",
    photo_shape: str = "rounded",
    font_family: str = "sans",
    title_size: int = 42,
    name_size: int = 52,
    role_size: int = 31,
    show_photo: bool = True,
    show_logo: bool = True,
    show_qr: bool = True,
    positions: dict[str, tuple[float, float, float, float]] | None = None,
    alignments: dict[str, str] | None = None,
    bold: dict[str, bool] | None = None,
    uppercase: dict[str, bool] | None = None,
    font_regular: Path | None = None,
    font_bold: Path | None = None,
) -> Image.Image:
    """Compone una credencial basada en objetos y posiciones normalizadas."""
    import qrcode

    accent = _hex_color(color, (23, 107, 135))
    background_rgb = _hex_color(background_color, (249, 250, 252))
    text_rgb = _hex_color(text_color, (23, 32, 43))
    card_size = (638, 1016) if orientation == "portrait" else (1016, 638)
    card = Image.new("RGB", card_size, background_rgb)
    if background:
        card.paste(ImageOps.fit(background.convert("RGB"), card_size, method=Image.Resampling.LANCZOS))
    draw = ImageDraw.Draw(card)
    if template == "sidebar":
        sidebar_width = .34 if orientation == "landscape" else .12
        draw.rectangle((0, 0, round(card_size[0] * sidebar_width), card_size[1]), fill=accent)
    elif template == "minimal":
        thickness = max(10, round(card_size[1] * 0.025))
        draw.rectangle((0, card_size[1] - thickness, card_size[0], card_size[1]), fill=accent)
    else:
        header_height = round(card_size[1] * (0.16 if orientation == "landscape" else 0.14))
        draw.rectangle((0, 0, card_size[0], header_height), fill=accent)
    draw.rounded_rectangle((3, 3, card_size[0] - 4, card_size[1] - 4), radius=28, outline=(211, 219, 229), width=4)

    layout = _card_positions(template, orientation)
    layout.update(positions or {})
    text_alignments = {"title": "left", "name": "left", "role": "left", **(alignments or {})}
    text_bold = {"title": True, "name": True, "role": False, **(bold or {})}
    text_uppercase = {"title": False, "name": False, "role": False, **(uppercase or {})}
    title_box = _pixel_box(layout["title"], card_size)
    title_text = (title or "CREDENCIAL").strip()[:80]
    if text_uppercase["title"]:
        title_text = title_text.upper()
    title_on_accent = template == "sidebar" and orientation == "landscape" and title_box[0] < card_size[0] * .34
    title_on_accent = title_on_accent or (template == "classic" and title_box[1] < card_size[1] * .17)
    title_path = font_bold if text_bold["title"] else font_regular
    title_font = _fit_text(draw, title_text, title_box[2] - title_box[0], title_size, text_bold["title"], font_family, title_path)
    _draw_aligned_text(draw, title_box, title_text, title_font, "white" if title_on_accent else accent, text_alignments["title"])

    if show_photo:
        photo_box = _pixel_box(layout["photo"], card_size)
        box_size = (max(1, photo_box[2] - photo_box[0]), max(1, photo_box[3] - photo_box[1]))
        photo = ImageOps.fit(portrait.convert("RGB"), box_size, method=Image.Resampling.LANCZOS)
        mask = Image.new("L", box_size, 0)
        mask_draw = ImageDraw.Draw(mask)
        if photo_shape == "circle":
            mask_draw.ellipse((0, 0, box_size[0] - 1, box_size[1] - 1), fill=255)
        elif photo_shape == "square":
            mask_draw.rectangle((0, 0, box_size[0], box_size[1]), fill=255)
        else:
            mask_draw.rounded_rectangle((0, 0, box_size[0], box_size[1]), radius=max(8, min(box_size) // 15), fill=255)
        card.paste(photo, photo_box[:2], mask)
        if photo_shape == "circle":
            draw.ellipse(photo_box, outline=(219, 225, 233), width=3)
        elif photo_shape == "square":
            draw.rectangle(photo_box, outline=(219, 225, 233), width=3)
        else:
            draw.rounded_rectangle(photo_box, radius=max(8, min(box_size) // 15), outline=(219, 225, 233), width=3)

    if show_logo and logo:
        logo_box = _pixel_box(layout["logo"], card_size)
        mark = logo.convert("RGBA")
        mark.thumbnail((logo_box[2] - logo_box[0], logo_box[3] - logo_box[1]), Image.Resampling.LANCZOS)
        x = logo_box[0] + (logo_box[2] - logo_box[0] - mark.width) // 2
        y = logo_box[1] + (logo_box[3] - logo_box[1] - mark.height) // 2
        card.paste(mark, (x, y), mark)

    safe_name = (name or "Sin nombre").strip()[:100]
    safe_role = (role or "").strip()[:120]
    if text_uppercase["name"]:
        safe_name = safe_name.upper()
    if text_uppercase["role"]:
        safe_role = safe_role.upper()
    name_box = _pixel_box(layout["name"], card_size)
    role_box = _pixel_box(layout["role"], card_size)
    name_path = font_bold if text_bold["name"] else font_regular
    name_font = _fit_text(draw, safe_name, name_box[2] - name_box[0], name_size, text_bold["name"], font_family, name_path)
    _draw_aligned_text(draw, name_box, safe_name, name_font, text_rgb, text_alignments["name"])
    if safe_role:
        role_fill = tuple(round(channel * .68 + background_rgb[index] * .32) for index, channel in enumerate(text_rgb))
        role_path = font_bold if text_bold["role"] else font_regular
        role_font = _fit_text(draw, safe_role, role_box[2] - role_box[0], role_size, text_bold["role"], font_family, role_path)
        _draw_aligned_text(draw, role_box, safe_role, role_font, role_fill, text_alignments["role"])

    if show_qr:
        qr_box = _pixel_box(layout["qr"], card_size)
        qr_size = max(20, min(qr_box[2] - qr_box[0], qr_box[3] - qr_box[1]))
        qr_data = (qr_value or safe_name).strip()
        qr = qrcode.make(qr_data).convert("RGB").resize((qr_size, qr_size), Image.Resampling.NEAREST)
        card.paste(qr, (qr_box[0], qr_box[1]))
    return card
