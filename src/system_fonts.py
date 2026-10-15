"""Catalogo seguro de fuentes locales para el diseñador de credenciales."""

from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


SUPPORTED_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}


@dataclass(frozen=True)
class FontFamily:
    id: str
    label: str
    css_family: str
    regular: Path
    bold: Path
    italic: Path
    bold_italic: Path


_LOCK = threading.Lock()
_CATALOG: dict[str, FontFamily] | None = None


def _font_directories() -> list[Path]:
    candidates = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Microsoft" / "Windows" / "Fonts")
    candidates.append(Path("/usr/share/fonts"))
    return [path for path in candidates if path.is_dir()]


def _choice_id(family: str) -> str:
    digest = hashlib.sha1(family.casefold().encode("utf-8")).hexdigest()[:12]
    return f"system:{digest}"


def _preference(style: str, *, bold: bool, italic: bool = False) -> tuple[int, int]:
    normalized = style.casefold()
    is_italic = "italic" in normalized or "oblique" in normalized
    italic_penalty = int(is_italic != italic)
    is_bold = any(word in normalized for word in ("bold", "black", "heavy", "semibold", "demi"))
    if bold:
        return (italic_penalty, 0 if is_bold else 2)
    regular = any(word in normalized for word in ("regular", "normal", "book", "roman", "italic", "oblique"))
    return (italic_penalty, 0 if regular and not is_bold else 1 if not is_bold else 3)


def _build_catalog() -> dict[str, FontFamily]:
    grouped: dict[str, list[tuple[Path, str]]] = {}
    seen_paths: set[Path] = set()
    for root in _font_directories():
        iterator = root.rglob("*") if root.name != "Fonts" else root.iterdir()
        for path in iterator:
            if not path.is_file() or path.suffix.casefold() not in SUPPORTED_FONT_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                family, style = ImageFont.truetype(str(path), 14).getname()
            except (OSError, ValueError):
                continue
            family = str(family).strip()
            if family:
                grouped.setdefault(family, []).append((resolved, str(style or "Regular")))

    catalog: dict[str, FontFamily] = {}
    for family, variants in grouped.items():
        regular = min(variants, key=lambda item: _preference(item[1], bold=False))[0]
        bold = min(variants, key=lambda item: _preference(item[1], bold=True))[0]
        italic = min(variants, key=lambda item: _preference(item[1], bold=False, italic=True))[0]
        bold_italic = min(variants, key=lambda item: _preference(item[1], bold=True, italic=True))[0]
        identifier = _choice_id(family)
        catalog[identifier] = FontFamily(identifier, family, family, regular, bold, italic, bold_italic)
    return catalog


def font_catalog() -> dict[str, FontFamily]:
    global _CATALOG
    if _CATALOG is None:
        with _LOCK:
            if _CATALOG is None:
                _CATALOG = _build_catalog()
    return _CATALOG


def public_font_catalog() -> list[dict[str, str]]:
    return [
        {"id": item.id, "label": item.label, "css_family": item.css_family}
        for item in sorted(font_catalog().values(), key=lambda font: font.label.casefold())
    ]


def resolve_font(identifier: str) -> tuple[Path | None, Path | None]:
    family = font_catalog().get(identifier)
    if family is None:
        return None, None
    return family.regular, family.bold


def resolve_font_variant(identifier: str, *, bold: bool = False, italic: bool = False) -> Path | None:
    """Devuelve el archivo de la variante pedida o None si la familia no es del sistema."""
    family = font_catalog().get(identifier)
    if family is None:
        return None
    if bold and italic:
        return family.bold_italic
    if italic:
        return family.italic
    return family.bold if bold else family.regular
