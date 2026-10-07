"""
Identidad visual de la empresa para los PDFs (logo, colores y datos de contacto).

Se lee de la compania de Odoo, se guarda en disco y en memoria (6 h) y nunca
lanza excepciones: si Odoo no responde usa la ultima copia guardada y, si no
hay ninguna, un estilo neutro sin logo. `branding_config.json` permite forzar
otro logo o colores sin tocar Odoo.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import fitz

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 6 * 3600
# Verde oscuro del isologo de Aramid; Odoo solo guarda rojo (primario) y negro.
DEFAULT_TABLE_COLOR = "#405c58"
NEUTRAL_ACCENT = "#3a4a5c"

_lock = threading.Lock()
_memory: Dict[str, Any] = {"at": 0.0, "data": None}


def _resolve_path(filename: str) -> Path:
    try:
        from config_manager import config_manager

        return Path(config_manager.get_config_directory()) / filename
    except Exception:
        import os

        base_dir = Path(os.environ.get("APPDATA", ".")) if os.name == "nt" else Path.home() / ".config"
        config_dir = base_dir / "EtiquetadorZPL"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / filename


def hex_to_rgb(value: Any, fallback: str = NEUTRAL_ACCENT) -> Tuple[float, float, float]:
    text = str(value or "").strip()
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", text):
        text = fallback
    text = text.lstrip("#")
    return tuple(int(text[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, False) else ""


def neutral_branding() -> Dict[str, Any]:
    return {
        "name": "",
        "logo": b"",
        "accent": NEUTRAL_ACCENT,
        "table": NEUTRAL_ACCENT,
        "address": "",
        "contact": "",
        "vat": "",
        "website": "",
        "source": "neutral",
    }


MAX_LOGO_WIDTH_PX = 700  # ~3x el ancho impreso: nitido sin inflar cada adjunto.


def _compact_logo(raw: bytes) -> bytes:
    """Achica logos grandes (el de Odoo viene en ~1700 px y pesa >100 KB por PDF)."""
    try:
        pixmap = fitz.Pixmap(raw)
        if pixmap.width <= MAX_LOGO_WIDTH_PX:
            return raw
        if pixmap.alpha:
            # JPEG no tiene transparencia: aplanar sobre blanco.
            pixmap = fitz.Pixmap(fitz.csRGB, pixmap, 0)
        scale = MAX_LOGO_WIDTH_PX / pixmap.width
        resized = fitz.Pixmap(pixmap, int(pixmap.width * scale), int(pixmap.height * scale), None)
        return resized.tobytes("jpeg", jpg_quality=90)
    except Exception as exc:
        logger.warning("No se pudo achicar el logo, se usa el original: %s", exc)
        return raw


def _from_odoo(company: Dict[str, Any]) -> Dict[str, Any]:
    logo = b""
    if company.get("logo"):
        try:
            logo = _compact_logo(base64.b64decode(company["logo"]))
        except (ValueError, TypeError):
            logo = b""
    address = ", ".join(part for part in (_text(company.get("street")), _text(company.get("street2")), _text(company.get("city"))) if part)
    website = re.sub(r"^https?://", "", _text(company.get("website"))).rstrip("/")
    contact = " · ".join(part for part in (_text(company.get("phone")), _text(company.get("email"))) if part)
    return {
        "name": _text(company.get("name")),
        "logo": logo,
        "accent": _text(company.get("primary_color")) or NEUTRAL_ACCENT,
        "table": DEFAULT_TABLE_COLOR,
        "address": address,
        "contact": contact,
        "vat": _text(company.get("vat")),
        "website": website,
        "source": "odoo",
    }


def _load_disk() -> Optional[Dict[str, Any]]:
    meta_path = _resolve_path("branding_cache.json")
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        logo_path = _resolve_path("branding_logo.bin")
        data["logo"] = logo_path.read_bytes() if logo_path.exists() else b""
        data["source"] = "cache"
        return data
    except Exception as exc:
        logger.warning("No se pudo leer el branding guardado: %s", exc)
        return None


def _save_disk(data: Dict[str, Any]) -> None:
    try:
        meta = {k: v for k, v in data.items() if k not in ("logo", "source")}
        _resolve_path("branding_cache.json").write_text(json.dumps(meta, ensure_ascii=True, indent=1), encoding="utf-8")
        _resolve_path("branding_logo.bin").write_bytes(data.get("logo") or b"")
    except Exception as exc:
        logger.warning("No se pudo guardar el branding: %s", exc)


def _apply_overrides(data: Dict[str, Any]) -> Dict[str, Any]:
    """`branding_config.json`: {"accent": "#hex", "table": "#hex", "logo_path": "C:/...png"}."""
    path = _resolve_path("branding_config.json")
    if not path.exists():
        return data
    try:
        overrides = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("branding_config.json invalido: %s", exc)
        return data
    result = dict(data)
    for key in ("accent", "table", "name", "address", "contact", "website", "vat"):
        if overrides.get(key):
            result[key] = str(overrides[key])
    logo_path = overrides.get("logo_path")
    if logo_path:
        try:
            result["logo"] = Path(logo_path).read_bytes()
        except OSError as exc:
            logger.warning("No se pudo leer el logo configurado %s: %s", logo_path, exc)
    return result


def get_branding(odoo: Any = None, force: bool = False) -> Dict[str, Any]:
    with _lock:
        cached = _memory["data"]
        if cached is not None and not force and time.time() - _memory["at"] < CACHE_TTL_SECONDS:
            return _apply_overrides(cached)

        data: Optional[Dict[str, Any]] = None
        if odoo is None:
            try:
                from odoo_integration import odoo_integration as odoo
            except Exception:
                odoo = None
        fetch = getattr(odoo, "get_company_branding", None)
        if fetch is not None and getattr(odoo, "is_configured", lambda: False)():
            try:
                company = fetch()
                if company:
                    data = _from_odoo(company)
                    _save_disk(data)
            except Exception as exc:
                logger.warning("No se pudo leer el branding desde Odoo: %s", exc)
        if data is None:
            data = cached or _load_disk() or neutral_branding()
        _memory["data"] = data
        _memory["at"] = time.time()
        return _apply_overrides(data)


def draw_header(page: Any, branding: Dict[str, Any], title: str, subtitle: str = "", margin: float = 40) -> float:
    """Dibuja logo + datos de la empresa + titulo. Devuelve la coordenada y siguiente."""
    width = page.rect.width
    top = margin - 8
    logo_bottom = top
    logo = branding.get("logo") or b""
    if logo:
        try:
            pixmap = fitz.Pixmap(logo)
            logo_h = 46.0
            logo_w = min(190.0, logo_h * pixmap.width / max(1, pixmap.height))
            rect = fitz.Rect(margin, top, margin + logo_w, top + logo_h)
            page.insert_image(rect, stream=logo, keep_proportion=True)
            logo_bottom = rect.y1
        except Exception as exc:
            logger.warning("No se pudo insertar el logo en el PDF: %s", exc)
            logo = b""
    if not logo and branding.get("name"):
        page.insert_text((margin, top + 24), branding["name"], fontname="hebo", fontsize=18, color=hex_to_rgb(branding.get("table")))
        logo_bottom = top + 30

    muted = (0.38, 0.42, 0.48)
    lines = [branding.get("address"), branding.get("contact"), f"RUT {branding['vat']}" if branding.get("vat") else "", branding.get("website")]
    y = top + 10
    for line in (text for text in lines if text):
        text_w = fitz.get_text_length(line, fontname="helv", fontsize=8)
        page.insert_text((width - margin - text_w, y), line, fontname="helv", fontsize=8, color=muted)
        y += 11

    y = max(logo_bottom, y) + 10
    page.draw_rect(fitz.Rect(margin, y, width - margin, y + 2.2), color=None, fill=hex_to_rgb(branding.get("accent")))
    y += 28
    page.insert_text((margin, y), title, fontname="hebo", fontsize=17, color=(0.1, 0.13, 0.17))
    if subtitle:
        y += 16
        page.insert_text((margin, y), subtitle, fontname="helv", fontsize=9, color=muted)
    return y + 18


def draw_footer(page: Any, branding: Dict[str, Any], text: str, margin: float = 40) -> None:
    width, height = page.rect.width, page.rect.height
    page.draw_line((margin, height - 38), (width - margin, height - 38), color=hex_to_rgb(branding.get("accent")), width=0.8)
    parts = [text] + [part for part in (branding.get("website"), branding.get("contact")) if part]
    page.insert_text((margin, height - 24), "   ·   ".join(parts), fontname="helv", fontsize=7.5, color=(0.38, 0.42, 0.48))
