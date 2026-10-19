"""Mejora de imagen de las fotos de credencial.

Dos herramientas independientes:

* ``auto_enhance``: mejora clasica con OpenCV, pensada para aplicarse a todo
  el lote. Reduce ruido, corrige el balance de blancos con los tonos neutros
  de la foto, levanta el contraste local (CLAHE sobre la luminancia) y enfoca
  suavemente. No inventa detalles.
* ``SuperResolver``: agranda con Real-ESRGAN (realesr-general-x4v3, ONNX) las
  fotos que tienen menos pixeles de los que necesita la caja de la credencial.
  Corre localmente con onnxruntime, sin conexion.

No se usan modelos de "restauracion de rostros" (GFPGAN, CodeFormer): inventan
rasgos y en una credencial de identificacion pueden cambiar a la persona.
"""

from __future__ import annotations

import math
import sys
import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

LEVELS = {"off": 0.0, "soft": 0.6, "normal": 1.0, "strong": 1.5}
MODEL_NAME = "realesr-general-x4v3.onnx"
UPSCALE_MARGIN = 1.15  # sólo se agranda si falta más de un 15 % de resolución
TOO_SMALL = 3.0  # con más de 3 veces de diferencia conviene pedir otra foto
AI_BLEND = 0.6  # mezcla con el agrandado común para conservar la textura de la piel
TILE = 256
TILE_PAD = 12


def _model_dirs() -> list[Path]:
    dirs = [Path(__file__).resolve().parent.parent / "models"]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        dirs.insert(0, Path(bundle) / "models")
    return dirs


def model_path() -> Path | None:
    for folder in _model_dirs():
        candidate = folder / MODEL_NAME
        if candidate.exists():
            return candidate
    return None


# --------------------------------------------------------------------------- #
# Mejora clásica
# --------------------------------------------------------------------------- #

def _white_balance(lab: np.ndarray, strength: float) -> None:
    """Lleva hacia el gris los tonos casi neutros (paredes, ropa clara, fondo)."""
    a = lab[..., 1] - 128.0
    b = lab[..., 2] - 128.0
    lightness = lab[..., 0]
    neutral = (np.abs(a) + np.abs(b) < 28) & (lightness > 40) & (lightness < 235)
    if neutral.mean() < 0.04:
        return  # casi no hay referencias neutras: mejor no tocar
    factor = min(1.0, 0.65 * strength)
    for channel, values in ((1, a), (2, b)):
        shift = float(np.clip(-values[neutral].mean() * factor, -12, 12))
        lab[..., channel] += shift


def auto_enhance(image: Image.Image, level: str = "normal", *, denoise: bool = True, sharpen: bool = True) -> Image.Image:
    """Ruido, balance de blancos, contraste local y enfoque, en proporción al nivel."""
    strength = LEVELS.get(level, 0.0)
    if strength <= 0:
        return image
    rgb = np.asarray(image.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if denoise:
        noise = 1.5 + 2.5 * strength
        bgr = cv2.fastNlMeansDenoisingColored(bgr, None, h=noise, hColor=noise, templateWindowSize=7, searchWindowSize=15)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    _white_balance(lab, strength)
    lightness = np.clip(lab[..., 0], 0, 255).astype(np.uint8)
    clahe = cv2.createCLAHE(clipLimit=1.2 + 0.8 * strength, tileGridSize=(8, 8))
    mix = min(0.6, 0.3 * strength)
    lab[..., 0] = lightness * (1 - mix) + clahe.apply(lightness).astype(np.float32) * mix
    bgr = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR).astype(np.float32)
    if not sharpen:
        return Image.fromarray(cv2.cvtColor(bgr.astype(np.uint8), cv2.COLOR_BGR2RGB))
    # Enfoque con máscara de desenfoque; el radio acompaña al tamaño de la foto.
    sigma = max(0.8, min(bgr.shape[:2]) / 450)
    blurred = cv2.GaussianBlur(bgr, (0, 0), sigma)
    detail = bgr - blurred
    detail[np.abs(detail) < 2.0] = 0  # no realza el grano fino que quedó
    bgr = np.clip(bgr + detail * (0.35 * strength), 0, 255).astype(np.uint8)
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


# --------------------------------------------------------------------------- #
# Superresolución
# --------------------------------------------------------------------------- #

class SuperResolver:
    """Real-ESRGAN x4 por mosaicos, para no usar mucha memoria con fotos medianas."""

    scale = 4

    def __init__(self, path: Path) -> None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.log_severity_level = 3
        self.session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.lock = threading.Lock()

    def _run(self, tile: np.ndarray) -> np.ndarray:
        tensor = np.ascontiguousarray(tile.transpose(2, 0, 1)[None].astype(np.float32) / 255.0)
        with self.lock:
            output = self.session.run(None, {self.input_name: tensor})[0][0]
        return np.clip(output.transpose(1, 2, 0) * 255.0, 0, 255)

    def upscale(self, image: Image.Image) -> Image.Image:
        source = np.asarray(image.convert("RGB"))
        height, width = source.shape[:2]
        scale = self.scale
        result = np.zeros((height * scale, width * scale, 3), np.float32)
        for top in range(0, height, TILE):
            for left in range(0, width, TILE):
                bottom, right = min(height, top + TILE), min(width, left + TILE)
                pad_top, pad_left = max(0, top - TILE_PAD), max(0, left - TILE_PAD)
                pad_bottom, pad_right = min(height, bottom + TILE_PAD), min(width, right + TILE_PAD)
                output = self._run(source[pad_top:pad_bottom, pad_left:pad_right])
                y0, x0 = (top - pad_top) * scale, (left - pad_left) * scale
                result[top * scale:bottom * scale, left * scale:right * scale] = output[y0:y0 + (bottom - top) * scale, x0:x0 + (right - left) * scale]
        return Image.fromarray(result.round().astype(np.uint8))


_RESOLVER: SuperResolver | None = None
_RESOLVER_FAILED = False
_RESOLVER_LOCK = threading.Lock()


def super_resolver() -> SuperResolver | None:
    """Modelo cargado una sola vez; None si falta el archivo o onnxruntime."""
    global _RESOLVER, _RESOLVER_FAILED
    if _RESOLVER is not None or _RESOLVER_FAILED:
        return _RESOLVER
    with _RESOLVER_LOCK:
        if _RESOLVER is None and not _RESOLVER_FAILED:
            path = model_path()
            try:
                _RESOLVER = SuperResolver(path) if path else None
            except Exception:  # noqa: BLE001 - sin el modelo se sigue con LANCZOS
                _RESOLVER = None
            _RESOLVER_FAILED = _RESOLVER is None
    return _RESOLVER


def missing_scale(size: tuple[int, int], target: tuple[int, int] | None) -> float:
    """Cuántas veces habría que agrandar el recorte para cubrir la caja (1 = alcanza)."""
    if not target:
        return 1.0
    return max(1.0, target[0] / max(1, size[0]), target[1] / max(1, size[1]))


def needs_upscale(size: tuple[int, int], target: tuple[int, int] | None) -> bool:
    return missing_scale(size, target) > UPSCALE_MARGIN


# --------------------------------------------------------------------------- #
# Combinación
# --------------------------------------------------------------------------- #

def improve(image: Image.Image, target: tuple[int, int] | None, *, level: str, upscale: bool) -> tuple[Image.Image, bool]:
    """Agranda si hace falta y aplica la mejora; devuelve (imagen, se usó IA)."""
    used_ai = False
    if upscale and needs_upscale(image.size, target):
        resolver = super_resolver()
        if resolver is not None:
            # El modelo limpia ruido y artefactos JPEG mientras agranda; mezclado con el
            # agrandado común conserva poros, pecas y textura (no queda "de plástico").
            upscaled = resolver.upscale(image)
            image = Image.blend(image.resize(upscaled.size, Image.Resampling.LANCZOS), upscaled, AI_BLEND)
            used_ai = True
    if target:
        # Se trabaja con un poco de margen sobre la caja: más rápido y sin perder nitidez.
        scale = max(target[0] / image.width, target[1] / image.height) * 1.25
        if scale < 1:
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    if LEVELS.get(level, 0) > 0:
        # Tras la IA sólo se corrigen color y contraste: más filtro de ruido o enfoque
        # suavizaría la piel o exageraría los bordes.
        image = auto_enhance(image, level, denoise=not used_ai, sharpen=not used_ai)
    return image, used_ai


def ceil_size(width: float, height: float) -> tuple[int, int]:
    return max(1, math.ceil(width)), max(1, math.ceil(height))
