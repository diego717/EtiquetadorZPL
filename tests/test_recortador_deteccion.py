"""Comparación y calibración del detector de rostros del recortador.

No abre ventanas ni importa customtkinter: trabaja directo contra `face_detection`
y contra `recortador_fotos.compute_face_crop`.

    python tests\\test_recortador_deteccion.py --fallback
    python tests\\test_recortador_deteccion.py --compare C:\\ruta\\a\\fotos
    python tests\\test_recortador_deteccion.py --crops   C:\\ruta\\a\\fotos

`--compare` es a la vez el chequeo de regresión y la herramienta que produce los
valores de BOX_SCALE_W / BOX_SCALE_H / BOX_SHIFT_Y de `face_detection.py`.

El camino "legacy" (Haar a resolución completa más la heurística de pares de ojos) está
copiado acá a propósito: es la línea base contra la que se mide, y tiene que sobrevivir
a que esa heurística se borre de la aplicación.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import face_detection  # noqa: E402
from recortador_fotos import SUPPORTED_EXTENSIONS, compute_face_crop  # noqa: E402


# --------------------------------------------------------------------------------------
# Línea base: exactamente lo que hacía la aplicación antes de YuNet.
# --------------------------------------------------------------------------------------

_legacy_face_cascade: Optional[cv2.CascadeClassifier] = None
_legacy_eye_cascade: Optional[cv2.CascadeClassifier] = None


def legacy_find_largest_face(image: Image.Image) -> Optional[tuple[int, int, int, int]]:
    global _legacy_face_cascade
    if _legacy_face_cascade is None:
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        _legacy_face_cascade = cv2.CascadeClassifier(str(path))
    if _legacy_face_cascade.empty():
        return None
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    faces = _legacy_face_cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(36, 36))
    if len(faces) == 0:
        return None
    return tuple(int(value) for value in max(faces, key=lambda face: face[2] * face[3]))


def legacy_find_eye_line(image: Image.Image, face: tuple[int, int, int, int]) -> Optional[float]:
    global _legacy_eye_cascade
    if _legacy_eye_cascade is None:
        path = Path(cv2.data.haarcascades) / "haarcascade_eye_tree_eyeglasses.xml"
        _legacy_eye_cascade = cv2.CascadeClassifier(str(path))
    if _legacy_eye_cascade.empty():
        return None
    face_x, face_y, face_w, face_h = face
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    roi_height = max(1, int(face_h * 0.62))
    roi = gray[face_y:face_y + roi_height, face_x:face_x + face_w]
    if roi.size == 0:
        return None
    candidates = _legacy_eye_cascade.detectMultiScale(
        roi, scaleFactor=1.10, minNeighbors=5,
        minSize=(max(12, int(face_w * 0.12)), max(12, int(face_h * 0.08))),
    )
    centers = [(face_x + x + w / 2, face_y + y + h / 2) for x, y, w, h in candidates]
    best_pair = None
    best_score = float("-inf")
    for index, first in enumerate(centers):
        for second in centers[index + 1:]:
            horizontal = abs(first[0] - second[0])
            vertical = abs(first[1] - second[1])
            if horizontal < face_w * 0.22 or vertical > face_h * 0.16:
                continue
            score = horizontal - vertical * 1.8
            if score > best_score:
                best_score, best_pair = score, (first, second)
    if best_pair:
        return (best_pair[0][1] + best_pair[1][1]) / 2
    return None


# --------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------

def iter_photos(folder: Path):
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def load(path: Path) -> Optional[Image.Image]:
    try:
        with Image.open(path) as source:
            return ImageOps.exif_transpose(source).copy()
    except Exception as error:
        print(f"  !! no se pudo leer {path.name}: {error}")
        return None


def summary(label: str, values: list[float]) -> str:
    if not values:
        return f"{label}: sin datos"
    median = statistics.median(values)
    if len(values) >= 4:
        quartiles = statistics.quantiles(values, n=4)
        spread = f", IQR {quartiles[0]:.3f}–{quartiles[2]:.3f}"
    else:
        spread = ""
    return f"{label}: mediana {median:.4f}{spread}  (n={len(values)})"


# --------------------------------------------------------------------------------------
# Modos
# --------------------------------------------------------------------------------------

def run_compare(folder: Path) -> int:
    print(f"Motor activo: {face_detection.engine()}  {face_detection.engine_reason()}")
    print(f"{'archivo':<38} {'haar':>18} {'yunet':>18} {'score':>6} {'roll':>7} {'ojos h/y':>9} {'ms h/y':>12}")
    print("-" * 118)

    ratios_w, ratios_h, offsets = [], [], []
    haar_hits = yunet_hits = haar_eyes = yunet_eyes = total = 0
    haar_ms, yunet_ms = [], []

    for path in iter_photos(folder):
        image = load(path)
        if image is None:
            continue
        total += 1

        start = time.perf_counter()
        haar_box = legacy_find_largest_face(image)
        haar_eye = legacy_find_eye_line(image, haar_box) if haar_box else None
        haar_elapsed = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        result = face_detection.detect_primary_face(image)
        yunet_elapsed = (time.perf_counter() - start) * 1000

        haar_ms.append(haar_elapsed)
        yunet_ms.append(yunet_elapsed)
        haar_hits += haar_box is not None
        yunet_hits += result is not None
        haar_eyes += haar_eye is not None
        yunet_eyes += result is not None and result.eye_line is not None

        haar_text = f"{haar_box[2]}x{haar_box[3]}" if haar_box else "—"
        if result:
            yunet_text = f"{result.box[2]}x{result.box[3]}"
            score_text, roll_text = f"{result.score:.2f}", f"{result.roll:+.1f}"
        else:
            yunet_text = score_text = roll_text = "—"

        # Sólo se calibra donde ambos detectan y coinciden en el mismo rostro.
        if haar_box and result and face_detection.same_face(result.box, haar_box):
            ratios_w.append(result.box[2] / haar_box[2])
            ratios_h.append(result.box[3] / haar_box[3])
            haar_cy = haar_box[1] + haar_box[3] / 2
            yunet_cy = result.box[1] + result.box[3] / 2
            offsets.append((yunet_cy - haar_cy) / haar_box[3])

        eyes_text = f"{'si' if haar_eye is not None else 'no'}/{'si' if result and result.eye_line is not None else 'no'}"
        print(f"{path.name[:38]:<38} {haar_text:>18} {yunet_text:>18} {score_text:>6} "
              f"{roll_text:>7} {eyes_text:>9} {haar_elapsed:>5.0f}/{yunet_elapsed:<5.0f}")

    if not total:
        print("No se encontraron fotos legibles en esa carpeta.")
        return 1

    print("-" * 118)
    print(f"Fotos analizadas: {total}")
    print(f"Detección  — haar {haar_hits}/{total} ({haar_hits/total:.0%})   yunet {yunet_hits}/{total} ({yunet_hits/total:.0%})")
    print(f"Línea ojos — haar {haar_eyes}/{total} ({haar_eyes/total:.0%})   yunet {yunet_eyes}/{total} ({yunet_eyes/total:.0%})")
    if haar_ms:
        print(f"Tiempo por foto — haar {statistics.median(haar_ms):.0f} ms   yunet {statistics.median(yunet_ms):.0f} ms")
    print()
    print("Calibración de la caja (sólo donde ambos detectan el mismo rostro):")
    print("  " + summary("yunet_w / haar_w", ratios_w))
    print("  " + summary("yunet_h / haar_h", ratios_h))
    print("  " + summary("desplazamiento vertical del centro / haar_h", offsets))
    if ratios_w and ratios_h:
        print()
        print("  Valores sugeridos para face_detection.py:")
        print(f"    BOX_SCALE_W = {1 / statistics.median(ratios_w):.3f}")
        print(f"    BOX_SCALE_H = {1 / statistics.median(ratios_h):.3f}")
        print(f"    BOX_SHIFT_Y = {-statistics.median(offsets):.3f}")
        print("  Si el IQR es ancho, las dos convenciones no mapean linealmente:")
        print("  dejar las escalas en 1.0 y ajustar face_fill una sola vez.")
    return 0


def run_crops(folder: Path, ratio: float, hair_margin: float, eye_position: float) -> int:
    print(f"Relación {ratio:.4f} · margen cabello {hair_margin:.2f} · ojos al {eye_position:.0f}%")
    print(f"{'archivo':<38} {'alto viejo':>11} {'alto nuevo':>11} {'delta':>8} {'delta %':>9}")
    print("-" * 82)

    deltas = []
    flagged = []
    for path in iter_photos(folder):
        image = load(path)
        if image is None:
            continue
        haar_box = legacy_find_largest_face(image)
        result = face_detection.detect_primary_face(image)
        if haar_box is None or result is None:
            print(f"{path.name[:38]:<38} {'—' if haar_box is None else '':>11} "
                  f"{'—' if result is None else '':>11} {'(un motor no detectó)':>18}")
            continue
        old_eye = legacy_find_eye_line(image, haar_box)
        old_crop = compute_face_crop(image.size, haar_box, old_eye, hair_margin, ratio, eye_position)
        new_crop = compute_face_crop(image.size, result.box, result.eye_line, hair_margin, ratio, eye_position)
        old_h, new_h = old_crop[3] - old_crop[1], new_crop[3] - new_crop[1]
        # Desplazamiento del centro del recorte, relativo al alto del recorte viejo.
        old_cy, new_cy = (old_crop[1] + old_crop[3]) / 2, (new_crop[1] + new_crop[3]) / 2
        delta = abs(new_cy - old_cy) + abs(new_h - old_h)
        fraction = delta / max(1.0, old_h)
        deltas.append(fraction)
        if fraction > 0.03:
            flagged.append((path.name, fraction))
        print(f"{path.name[:38]:<38} {old_h:>11.0f} {new_h:>11.0f} {delta:>8.0f} {fraction:>8.1%}")

    print("-" * 82)
    if deltas:
        print(f"Delta de recorte — mediana {statistics.median(deltas):.2%} (objetivo: bajo 2%)")
    if flagged:
        print(f"\n{len(flagged)} foto(s) por encima del 3%, revisar a ojo:")
        for name, fraction in sorted(flagged, key=lambda pair: -pair[1])[:20]:
            print(f"  {fraction:>7.1%}  {name}")
    return 0


def run_fallback() -> int:
    """Cada degradación tiene que aterrizar en Haar, no tirar una excepción."""
    sample = Image.new("RGB", (640, 480), "white")
    failures = 0

    def check(label: str, expected: str) -> None:
        nonlocal failures
        try:
            actual = face_detection.engine()
            face_detection.detect_primary_face(sample)
        except Exception as error:
            print(f"  FALLA  {label}: tiró {type(error).__name__}: {error}")
            failures += 1
            return
        if actual != expected:
            print(f"  FALLA  {label}: motor {actual!r}, se esperaba {expected!r}")
            failures += 1
            return
        print(f"  ok     {label}: motor {actual!r} · {face_detection.engine_note() or 'sin aviso'}")

    print("Degradaciones del detector:")

    face_detection.reset()
    check("modelo presente", "yunet")

    original_name = face_detection.MODEL_FILENAME
    face_detection.MODEL_FILENAME = "no_existe_este_modelo.onnx"
    face_detection.reset()
    check("modelo faltante", "haar")
    face_detection.MODEL_FILENAME = original_name

    truncated = Path(__file__).resolve().parent / "_modelo_truncado.onnx"
    real = face_detection.model_path()
    try:
        truncated.write_bytes(real.read_bytes()[:512] if real else b"basura")
        original_model_path = face_detection.model_path
        face_detection.model_path = lambda: truncated
        face_detection.reset()
        check("modelo corrupto", "haar")
        face_detection.model_path = original_model_path
    finally:
        truncated.unlink(missing_ok=True)

    saved = getattr(cv2, "FaceDetectorYN", None)
    if saved is not None:
        del cv2.FaceDetectorYN
        face_detection.reset()
        check("OpenCV sin FaceDetectorYN", "haar")
        cv2.FaceDetectorYN = saved

    face_detection.reset()
    check("restaurado", "yunet")

    print(f"\n{'TODO OK' if not failures else str(failures) + ' FALLA(S)'}")
    return 1 if failures else 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--compare", metavar="CARPETA", help="Haar vs YuNet, con estadísticas de calibración")
    group.add_argument("--crops", metavar="CARPETA", help="Encuadre resultante viejo vs nuevo")
    group.add_argument("--fallback", action="store_true", help="Verifica las degradaciones del detector")
    parser.add_argument("--ratio", type=float, default=3 / 4, help="Relación de aspecto para --crops (por defecto 3:4)")
    parser.add_argument("--hair-margin", type=float, default=0.20, help="Margen de cabello 0-0.4 para --crops")
    parser.add_argument("--eye-position", type=float, default=40.0, help="Posición de ojos en %% para --crops")
    args = parser.parse_args(argv)

    if args.fallback:
        return run_fallback()

    folder = Path(args.compare or args.crops).expanduser()
    if not folder.is_dir():
        print(f"No es una carpeta: {folder}")
        return 1
    if args.compare:
        return run_compare(folder)
    return run_crops(folder, args.ratio, args.hair_margin, args.eye_position)


if __name__ == "__main__":
    raise SystemExit(main())
