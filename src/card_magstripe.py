"""Codificacion de banda magnetica a traves del controlador de la impresora.

Igual que CardExchange o TrustID, los datos de cada pista viajan como texto en
la pagina de la tarjeta, rodeados de los comandos que reconoce el controlador
de cada marca (por ejemplo ``~1DATO`` en Magicard o Entrust). El controlador
detecta esos textos, los quita de la impresion y los graba en la banda.

Si el controlador no tiene activado el procesamiento de comandos o macros de
codificacion, el texto se imprime en la tarjeta: por eso conviene hacer una
tarjeta de prueba y revisar la configuracion de codificacion en Windows.

Los datos se validan con las reglas ISO 7811 (pistas de alta y baja coercitividad):
la pista 1 admite letras mayusculas, numeros y algunos signos (hasta 76
caracteres); las pistas 2 y 3, numeros y el separador ``=`` (hasta 37 y 104).
Los centinelas de inicio y fin (``%``, ``;`` y ``?``) los agrega la impresora.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

TRACKS = (1, 2, 3)
TRACK_LIMITS = {1: 76, 2: 37, 3: 104}
# Pista 1: juego de 6 bits ISO (ASCII 0x20-0x5F) sin los centinelas % y ?.
TRACK1_ALLOWED = {chr(code) for code in range(0x20, 0x60)} - {"%", "?"}
NUMERIC_ALLOWED = set("0123456789=")


@dataclass(frozen=True)
class MagProfile:
    id: str
    label: str
    start: str
    end: str
    pattern: str
    note: str


# ``{n}`` se reemplaza por el numero de pista. Los valores se pueden editar en el
# dialogo de impresion por si el controlador esta configurado distinto.
PROFILES: tuple[MagProfile, ...] = (
    MagProfile(
        "magicard", "Magicard (Enduro, Rio Pro, 300, 600, Pronto)", "~{n}", "",
        r"magicard|enduro|rio ?pro|600 ?neo|300 ?neo|pronto|ultima|tango",
        "En el controlador: Codificación › Activar el procesamiento de macros (Enable macro processing).",
    ),
    MagProfile(
        "entrust", "Entrust / Datacard (XPS Card Printer: Sigma, CD800, CR805, SD)", "~{n}", "",
        r"entrust|datacard|xps card|sigma|\bcd ?8\d\d|\bcr ?8\d\d|\bsd ?\d{3}",
        "En el controlador XPS: Banda magnética › usar escapes de texto (~1, ~2, ~3).",
    ),
    MagProfile(
        "zebra", "Zebra (ZXP, ZC100/300)", "${{{n}", "}}$",
        r"zebra|zxp|\bzc ?[1-3]\d\d",
        "En el controlador Zebra: Codificación › Codificación magnética con macros activada. Si tu controlador usa ~1=, cambiá los comandos.",
    ),
    MagProfile(
        "evolis", "Evolis (Primacy, Zenius)", "|{n}", "|",
        r"evolis|primacy|zenius|badgy",
        "En Evolis Print Center: Codificación magnética › texto delimitado por |.",
    ),
    MagProfile(
        "fargo", "HID Fargo (DTC, HDP)", "~{n}", "",
        r"fargo|\bdtc ?\d|\bhdp ?\d",
        "En el controlador Fargo: Magnetic Encoding › Enable text with ~1, ~2, ~3.",
    ),
    MagProfile(
        "swiftpro", "Swiftpro (K30, K60, P20)", "~{n}", "",
        r"swift ?pro|\bk ?[36]0\b",
        "Formato a confirmar con una tarjeta de prueba: revisá la configuración de codificación del controlador Swiftpro.",
    ),
    MagProfile("custom", "Personalizado", "~{n}", "", r"^$", "Escribí los comandos de inicio y fin que usa tu controlador."),
)
PROFILE_BY_ID = {profile.id: profile for profile in PROFILES}


def detect_profile(printer: str, driver: str = "") -> MagProfile:
    text = f"{printer} {driver}"
    for profile in PROFILES:
        if profile.id != "custom" and re.search(profile.pattern, text, re.IGNORECASE):
            return profile
    return PROFILE_BY_ID["magicard"]


def public_profiles() -> list[dict]:
    return [
        {"id": profile.id, "label": profile.label, "note": profile.note,
         "start": [profile.start.format(n=track) for track in TRACKS],
         "end": [profile.end.format(n=track) for track in TRACKS],
         "pattern": profile.pattern}
        for profile in PROFILES
    ]


def normalize_track(track: int, value: str) -> str:
    """Limpia el dato: quita espacios sobrantes y centinelas escritos a mano; pista 1 en mayúsculas."""
    value = str(value or "").strip()
    if track == 1:
        value = value.upper()
        if value.startswith("%"):
            value = value[1:]
    elif value.startswith(";"):
        value = value[1:]
    if value.endswith("?"):
        value = value[:-1]
    return value


def track_error(track: int, value: str) -> str | None:
    """Mensaje de error en castellano, o None si el dato se puede grabar."""
    if not value:
        return None
    limit = TRACK_LIMITS[track]
    if len(value) > limit:
        return f"pista {track}: {len(value)} caracteres, admite hasta {limit}"
    allowed = TRACK1_ALLOWED if track == 1 else NUMERIC_ALLOWED
    invalid = sorted({char for char in value if char not in allowed})
    if invalid:
        shown = " ".join(repr(char) if char.strip() else "espacio" for char in invalid[:6])
        kind = "letras sin acentos, números y signos básicos" if track == 1 else "sólo números y ="
        return f"pista {track}: caracteres no admitidos {shown} ({kind})"
    return None


def resolve_tracks(templates: Mapping, values: Mapping[str, str], resolve) -> dict[int, str]:
    """Datos finales de cada pista para una credencial (``resolve`` reemplaza los campos)."""
    result = {}
    for track in TRACKS:
        template = str(templates.get(f"track{track}") or "")
        if template.strip():
            result[track] = normalize_track(track, resolve(template, values))
    return result


def encoding_strings(tracks: Mapping[int, str], start: list[str], end: list[str]) -> list[str]:
    """Textos que se dibujan en la página para que el controlador los grabe."""
    strings = []
    for track in TRACKS:
        data = tracks.get(track)
        if data:
            strings.append(f"{start[track - 1]}{data}{end[track - 1]}")
    return strings
