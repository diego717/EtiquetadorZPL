"""Detección de rostros para el recortador de fotos.

Usa YuNet (el detector DNN que trae OpenCV) y cae a los Haar cascades clásicos
cuando el modelo no está disponible. El módulo no importa tkinter a propósito:
así se puede ejercitar sin abrir una ventana desde `tests/test_recortador_deteccion.py`.

El modelo es un archivo local vendorizado en `models/`. No hay descarga en runtime:
la aplicación sigue trabajando completamente offline.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image


MODEL_FILENAME = "face_detection_yunet_2023mar.onnx"
MEDIAPIPE_MODEL_FILENAMES = ("blaze_face_short_range.tflite",)

DETECTOR_LABELS = ("YuNet + MediaPipe", "MediaPipe", "YuNet", "Clasico Haar")
_DETECTOR_ALIASES = {
    "auto": "auto",
    "yunet + mediapipe": "auto",
    "yunet+mediapipe": "auto",
    "mediapipe": "mediapipe",
    "mp": "mediapipe",
    "yunet": "yunet",
    "haar": "haar",
    "clasico haar": "haar",
    "clásico haar": "haar",
}
_DETECTOR_LABEL_BY_KEY = {
    "auto": "YuNet + MediaPipe",
    "mediapipe": "MediaPipe",
    "yunet": "YuNet",
    "haar": "Clasico Haar",
}

# Lado mayor al que se reduce la foto antes de detectar. Un rostro en el umbral de
# "rostro pequeño" del control de calidad (12% del alto) queda en ~115 px acá, y uno
# del 3% queda en ~29 px: cómodo para YuNet. Por debajo de ~640 se empiezan a perder
# rostros chicos de verdad.
DETECT_LONG_SIDE = 960

SCORE_THRESHOLD = 0.7
NMS_THRESHOLD = 0.3
TOP_K = 50

# Parámetros del Haar heredado. Se mantienen idénticos a los originales para que el
# camino de respaldo se comporte exactamente como la versión anterior.
HAAR_SCALE_FACTOR = 1.12
HAAR_MIN_NEIGHBORS = 5
HAAR_MIN_SIZE = (36, 36)

# Ajuste de la caja de YuNet a la convención de Haar. `apply_face_crop`, la semilla de
# grabCut, el umbral de "rostro pequeño" y la composición de tarjeta asumen todos cajas
# con la proporción que devolvía Haar (siempre cuadradas, ventana de 24×24). Se calibran
# empíricamente con `tests/test_recortador_deteccion.py --compare`; en identidad no alteran
# nada.
BOX_SCALE_W = 1.0
BOX_SCALE_H = 1.0
BOX_SHIFT_Y = 0.0

# MediaPipe/BlazeFace devuelve una caja muy ajustada al rostro. El recortador
# necesita una caja comparable a YuNet/Haar para calcular un encuadre de
# credencial con cuello y hombros.
MEDIAPIPE_BOX_SCALE_W = 1.45
MEDIAPIPE_BOX_SCALE_H = 1.60
MEDIAPIPE_BOX_SHIFT_Y = 0.08

# Tras esta cantidad de fallos seguidos de detect() se abandona YuNet por la sesión.
MAX_CONSECUTIVE_FAILURES = 3


@dataclass(frozen=True)
class FaceResult:
    """Rostro principal de una foto, en coordenadas de la imagen completa."""

    box: tuple[int, int, int, int]
    eye_line: Optional[float]
    eye_points: Optional[tuple[tuple[float, float], tuple[float, float]]]
    roll: float
    score: float
    engine: str


def _normalize_detector(value: object) -> str:
    text = str(value or "auto").strip().lower()
    return _DETECTOR_ALIASES.get(text, "auto")


_state: dict = {
    "engine": None,
    "detector": None,
    "reason": "",
    "failures": 0,
    "preference": _normalize_detector(os.environ.get("RECORTADOR_FACE_DETECTOR", "auto")),
}
_mediapipe_detector = None
_mediapipe_reason = ""

# Memo de un solo lugar: `find_largest_face` y `find_eye_line` se llaman en secuencia
# sobre la misma foto y no tiene sentido correr la red dos veces. Se guarda una
# referencia fuerte a la imagen para que `id()` no pueda reciclarse en otro objeto.
_cache: Optional[tuple[int, Image.Image, Optional[FaceResult]]] = None


def _resource_dir() -> Path:
    """Carpeta base de recursos, tanto en desarrollo como dentro del exe de PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent


def model_path() -> Optional[Path]:
    candidates = (
        _resource_dir() / "models" / MODEL_FILENAME,
        Path(__file__).resolve().parent / "models" / MODEL_FILENAME,
        Path.cwd() / "models" / MODEL_FILENAME,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def mediapipe_model_path() -> Optional[Path]:
    base_dirs = (
        _resource_dir() / "models",
        Path(__file__).resolve().parent / "models",
        Path.cwd() / "models",
    )
    for filename in MEDIAPIPE_MODEL_FILENAMES:
        for base_dir in base_dirs:
            candidate = base_dir / filename
            if candidate.is_file():
                return candidate
    return None


def _load_yunet():
    if not hasattr(cv2, "FaceDetectorYN"):
        return None, f"OpenCV {cv2.__version__} no incluye FaceDetectorYN"
    path = model_path()
    if path is None:
        return None, f"no se encontró {MODEL_FILENAME}"
    try:
        detector = cv2.FaceDetectorYN.create(
            str(path), "", (320, 320), SCORE_THRESHOLD, NMS_THRESHOLD, TOP_K
        )
        return detector, ""
    except Exception as error:
        # cv::dnn::readNet abre la ruta con un stream de char angosto: un perfil como
        # C:\Users\José\... falla acá pero funciona pasando el modelo como buffer.
        try:
            buffer = np.frombuffer(path.read_bytes(), dtype=np.uint8)
            detector = cv2.FaceDetectorYN.create(
                "onnx", buffer, np.empty(0, np.uint8), (320, 320),
                SCORE_THRESHOLD, NMS_THRESHOLD, TOP_K,
            )
            return detector, ""
        except Exception as buffer_error:
            return None, f"OpenCV {cv2.__version__}: {error} / {buffer_error}"


def _load_haar():
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        return None, "no se pudo cargar el detector clásico de OpenCV"
    return cascade, ""


def _load_mediapipe():
    global _mediapipe_detector, _mediapipe_reason
    if _mediapipe_detector is not None:
        return _mediapipe_detector, ""
    if _mediapipe_reason:
        return None, _mediapipe_reason
    path = mediapipe_model_path()
    if path is None:
        _mediapipe_reason = "no se encontro un modelo de MediaPipe"
        return None, _mediapipe_reason
    try:
        import mediapipe as mp

        base_options = mp.tasks.BaseOptions(model_asset_path=str(path))
        options = mp.tasks.vision.FaceDetectorOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            min_detection_confidence=0.50,
            min_suppression_threshold=0.30,
        )
        _mediapipe_detector = mp.tasks.vision.FaceDetector.create_from_options(options)
        return _mediapipe_detector, ""
    except Exception as error:
        _mediapipe_reason = f"MediaPipe no disponible: {error}"
        return None, _mediapipe_reason


def _ensure_engine() -> None:
    """Resuelve el motor una sola vez por sesión."""
    if _state["engine"] is not None:
        return
    preference = _state.get("preference", "auto")
    reasons: list[str] = []
    if preference in ("auto", "yunet"):
        detector, reason = _load_yunet()
        if detector is not None:
            _state.update(engine="yunet", detector=detector, reason="")
            return
        reasons.append(reason)
    if preference in ("auto", "mediapipe"):
        detector, reason = _load_mediapipe()
        if detector is not None:
            _state.update(engine="mediapipe", detector=detector, reason="")
            return
        reasons.append(reason)
    cascade, haar_reason = _load_haar()
    if cascade is not None:
        _state.update(engine="haar", detector=cascade, reason="; ".join(reason for reason in reasons if reason))
        return
    reasons.append(haar_reason)
    _state.update(engine="none", detector=None, reason="; ".join(reason for reason in reasons if reason))


def _fall_back_to_haar(reason: str) -> None:
    cascade, haar_reason = _load_haar()
    if cascade is not None:
        _state.update(engine="haar", detector=cascade, reason=reason, failures=0)
    else:
        _state.update(engine="none", detector=None, reason=f"{reason}; {haar_reason}")


def detector_preference() -> str:
    return _state.get("preference", "auto")


def detector_preference_label() -> str:
    return _DETECTOR_LABEL_BY_KEY.get(detector_preference(), "YuNet + MediaPipe")


def set_detector_preference(value: object) -> None:
    global _cache
    preference = _normalize_detector(value)
    if preference == _state.get("preference") and _state["engine"] is not None:
        return
    _state.update(engine=None, detector=None, reason="", failures=0, preference=preference)
    _cache = None


def engine() -> str:
    """`"yunet"`, `"mediapipe"`, `"haar"` o `"none"`."""
    _ensure_engine()
    return _state["engine"]


def engine_note() -> str:
    """Mensaje breve para la barra de estado, vacío cuando el detector avanzado está activo."""
    if engine() == "yunet":
        return ""
    if engine() == "mediapipe":
        return "Detector MediaPipe activo."
    if engine() == "haar":
        return "Detector avanzado no disponible; se usó el detector clásico."
    return "No hay detector de rostros disponible."


def engine_reason() -> str:
    """Motivo técnico de la degradación, para soporte."""
    _ensure_engine()
    return _state["reason"]


def reset() -> None:
    """Vuelve a resolver el motor y limpia el memo. Sólo lo usan las pruebas."""
    global _cache
    _state.update(engine=None, detector=None, reason="", failures=0)
    _cache = None


def _prepare(image: Image.Image) -> tuple[np.ndarray, float, float]:
    """Reduce en PIL y devuelve BGR más los factores para volver a la escala original.

    Reducir con PIL y no con numpy evita materializar un array de 72 MB por una foto de 24 MP.
    """
    source = image if image.mode in ("RGB", "L") else image.convert("RGB")
    width, height = source.size
    longest = max(width, height)
    if longest > DETECT_LONG_SIDE:
        factor = DETECT_LONG_SIDE / longest
        target = (max(1, round(width * factor)), max(1, round(height * factor)))
        source = source.resize(target, Image.Resampling.BILINEAR)
    rgb = np.asarray(source.convert("RGB"))
    # Los factores salen de los tamaños logrados, no del factor pedido: el redondeo
    # si no corre la caja uno o dos píxeles en el eje largo.
    scale_x = width / rgb.shape[1]
    scale_y = height / rgb.shape[0]
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), scale_x, scale_y


def _scale_box(x: float, y: float, w: float, h: float, scale_x: float, scale_y: float) -> tuple[int, int, int, int]:
    """Lleva la caja a coordenadas completas y la normaliza a la convención de Haar."""
    x, w = x * scale_x, w * scale_x
    y, h = y * scale_y, h * scale_y
    new_w, new_h = w * BOX_SCALE_W, h * BOX_SCALE_H
    # Se escala respecto del centro para no correr el rostro al normalizar.
    x -= (new_w - w) / 2
    y -= (new_h - h) / 2
    y += new_h * BOX_SHIFT_Y
    return int(round(x)), int(round(y)), int(round(new_w)), int(round(new_h))


def _scale_mediapipe_box(x: float, y: float, w: float, h: float, scale_x: float, scale_y: float) -> tuple[int, int, int, int]:
    x, w = x * scale_x, w * scale_x
    y, h = y * scale_y, h * scale_y
    new_w = w * MEDIAPIPE_BOX_SCALE_W
    new_h = h * MEDIAPIPE_BOX_SCALE_H
    x -= (new_w - w) / 2
    y -= (new_h - h) / 2
    y += new_h * MEDIAPIPE_BOX_SHIFT_Y
    return int(round(x)), int(round(y)), int(round(new_w)), int(round(new_h))


def _eye_line_from(
    eyes: tuple[tuple[float, float], tuple[float, float]]
) -> tuple[float, float]:
    """Devuelve (línea de ojos, inclinación en grados)."""
    # Ordenar por x y no por el nombre del landmark: YuNet llama "derecho" al ojo del
    # sujeto, que cae del lado izquierdo de la imagen.
    left, right = sorted(eyes, key=lambda point: point[0])
    line = (left[1] + right[1]) / 2
    roll = math.degrees(math.atan2(right[1] - left[1], max(1e-6, right[0] - left[0])))
    return line, roll


def _detect_yunet(bgr: np.ndarray, scale_x: float, scale_y: float) -> Optional[FaceResult]:
    detector = _state["detector"]
    height, width = bgr.shape[:2]
    # setInputSize toma (ancho, alto), al revés que .shape. YuNet no redimensiona solo.
    detector.setInputSize((width, height))
    _retval, faces = detector.detect(bgr)
    if faces is None or len(faces) == 0:
        return None
    # YuNet ordena por score, pero al recortador le interesa el rostro principal:
    # el más grande, igual que hacía find_largest_face con Haar.
    row = max(faces, key=lambda face: float(face[2]) * float(face[3]))
    box = _scale_box(float(row[0]), float(row[1]), float(row[2]), float(row[3]), scale_x, scale_y)
    eyes = (
        (float(row[4]) * scale_x, float(row[5]) * scale_y),
        (float(row[6]) * scale_x, float(row[7]) * scale_y),
    )
    eye_line, roll = _eye_line_from(eyes)
    return FaceResult(box, eye_line, eyes, roll, float(row[14]), "yunet")


def _detect_mediapipe(
    bgr: np.ndarray,
    scale_x: float,
    scale_y: float,
    detector=None,
) -> Optional[FaceResult]:
    import mediapipe as mp

    detector = detector or _state["detector"]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = detector.detect(image)
    detections = getattr(result, "detections", None)
    if not detections:
        return None
    height, width = rgb.shape[:2]
    detection = max(
        detections,
        key=lambda item: item.bounding_box.width * item.bounding_box.height,
    )
    box_data = detection.bounding_box
    box = _scale_mediapipe_box(
        box_data.origin_x,
        box_data.origin_y,
        box_data.width,
        box_data.height,
        scale_x,
        scale_y,
    )
    keypoints = list(detection.keypoints or [])
    eyes = None
    eye_line = None
    roll = 0.0
    if len(keypoints) >= 2:
        eyes = (
            (keypoints[0].x * width * scale_x, keypoints[0].y * height * scale_y),
            (keypoints[1].x * width * scale_x, keypoints[1].y * height * scale_y),
        )
        eye_line, roll = _eye_line_from(eyes)
    score = float(detection.categories[0].score) if detection.categories else 0.0
    return FaceResult(box, eye_line, eyes, roll, score, "mediapipe")


def _detect_mediapipe_fallback(bgr: np.ndarray, scale_x: float, scale_y: float) -> Optional[FaceResult]:
    detector, _reason = _load_mediapipe()
    if detector is None:
        return None
    try:
        return _detect_mediapipe(bgr, scale_x, scale_y, detector)
    except Exception:
        return None


def _detect_haar(bgr: np.ndarray, scale_x: float, scale_y: float) -> Optional[FaceResult]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    faces = _state["detector"].detectMultiScale(
        gray, scaleFactor=HAAR_SCALE_FACTOR, minNeighbors=HAAR_MIN_NEIGHBORS, minSize=HAAR_MIN_SIZE
    )
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda face: face[2] * face[3])
    # Sin línea de ojos: la heurística de pares de cascades se retiró junto con Haar.
    # apply_face_crop degrada a la rama de hair_margin, igual que cuando fallaba.
    box = (
        int(round(x * scale_x)), int(round(y * scale_y)),
        int(round(w * scale_x)), int(round(h * scale_y)),
    )
    return FaceResult(box, None, None, 0.0, 0.0, "haar")


def _detect_uncached(image: Image.Image) -> Optional[FaceResult]:
    _ensure_engine()
    if _state["engine"] == "none":
        return None
    bgr, scale_x, scale_y = _prepare(image)
    if _state["engine"] == "haar":
        try:
            return _detect_haar(bgr, scale_x, scale_y)
        except cv2.error:
            return None
    if _state["engine"] == "mediapipe":
        try:
            return _detect_mediapipe(bgr, scale_x, scale_y)
        except Exception:
            return None
    try:
        result = _detect_yunet(bgr, scale_x, scale_y)
    except cv2.error as error:
        _state["failures"] += 1
        if _state["failures"] >= MAX_CONSECUTIVE_FAILURES:
            _fall_back_to_haar(f"detect() falló {_state['failures']} veces: {error}")
        if _state.get("preference") == "auto":
            return _detect_mediapipe_fallback(bgr, scale_x, scale_y)
        return None
    _state["failures"] = 0
    if result is None and _state.get("preference") == "auto":
        return _detect_mediapipe_fallback(bgr, scale_x, scale_y)
    return result


def detect_primary_face(image: Image.Image) -> Optional[FaceResult]:
    """Rostro principal de la foto, o None. Memoiza la última imagen consultada."""
    global _cache
    if _cache is not None and _cache[0] == id(image) and _cache[1] is image:
        return _cache[2]
    result = _detect_uncached(image)
    _cache = (id(image), image, result)
    return result


def same_face(box: tuple[int, int, int, int], other: tuple[int, int, int, int]) -> bool:
    """¿Las dos cajas señalan el mismo rostro?

    Comparación deliberadamente laxa (centro dentro de la otra caja inflada un 20%): un IoU
    estricto rechazaría cajas legítimamente renormalizadas.
    """
    x, y, w, h = other
    margin_x, margin_y = w * 0.20, h * 0.20
    center_x, center_y = box[0] + box[2] / 2, box[1] + box[3] / 2
    return (x - margin_x <= center_x <= x + w + margin_x
            and y - margin_y <= center_y <= y + h + margin_y)
