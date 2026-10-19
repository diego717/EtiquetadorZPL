"""Geometria vectorial de las credenciales.

Un trazado (objeto ``path``) es una lista de subtrazados. Cada subtrazado tiene
nodos con su punto ``p`` y, opcionalmente, el manejador de entrada ``i`` y el de
salida ``o`` (curvas Bezier cubicas, igual que la herramienta Forma de Corel).
Las coordenadas son fracciones de la caja del objeto, de modo que el trazado se
estira con el objeto; los grosores de linea se miden en puntos y no se deforman.

Este modulo no conoce FastAPI ni el resto del motor: dibuja mascaras, calcula
contornos con Shapely, hace operaciones booleanas, pasa texto a curvas y prepara
los logos SVG para la salida en mapa de bits o vectorial.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw

KAPPA = 0.5522847498307936
SUPERSAMPLE = 3
MITER_LIMIT = 10.0
DASH_PATTERNS = {"dash": (4.0, 2.0), "dot": (1.0, 1.5), "dashdot": (4.0, 2.0, 1.0, 2.0)}

Point = tuple[float, float]


# --------------------------------------------------------------------------- #
# Trazados
# --------------------------------------------------------------------------- #

def _point(value) -> Point | None:
    if value is None:
        return None
    return float(value[0]), float(value[1])


def node(p: Point, i: Point | None = None, o: Point | None = None) -> dict:
    return {"p": p, "i": i, "o": o}


def normalize_paths(paths: Iterable[Mapping] | None) -> list[dict]:
    """Copia los subtrazados con tuplas de float y descarta nodos invalidos."""
    result = []
    for subpath in paths or []:
        nodes = []
        for entry in subpath.get("nodes") or []:
            point = _point(entry.get("p"))
            if point is None:
                continue
            nodes.append(node(point, _point(entry.get("i")), _point(entry.get("o"))))
        if nodes:
            result.append({"closed": bool(subpath.get("closed")), "nodes": nodes})
    return result


def map_paths(paths: Sequence[Mapping], transform) -> list[dict]:
    """Aplica ``transform(x, y)`` a puntos y manejadores."""
    mapped = []
    for subpath in paths:
        nodes = []
        for entry in subpath["nodes"]:
            nodes.append(node(
                transform(*entry["p"]),
                transform(*entry["i"]) if entry.get("i") else None,
                transform(*entry["o"]) if entry.get("o") else None,
            ))
        mapped.append({"closed": subpath["closed"], "nodes": nodes})
    return mapped


def scale_paths(paths: Sequence[Mapping], sx: float, sy: float, dx: float = 0, dy: float = 0) -> list[dict]:
    return map_paths(paths, lambda x, y: (x * sx + dx, y * sy + dy))


def segments(subpath: Mapping) -> Iterator[tuple[Point, Point | None, Point | None, Point]]:
    """Tramos del subtrazado: (p0, c1, c2, p3); c1 y c2 son None en las rectas."""
    nodes = subpath["nodes"]
    count = len(nodes) if subpath.get("closed") and len(nodes) > 1 else len(nodes) - 1
    for index in range(max(0, count)):
        start = nodes[index]
        end = nodes[(index + 1) % len(nodes)]
        c1, c2 = start.get("o"), end.get("i")
        if c1 is None and c2 is None:
            yield start["p"], None, None, end["p"]
        else:
            yield start["p"], c1 or start["p"], c2 or end["p"], end["p"]


def rect_paths(x0: float, y0: float, x1: float, y1: float, radius: float = 0) -> list[dict]:
    radius = max(0.0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    if radius <= 0:
        return [{"closed": True, "nodes": [node((x0, y0)), node((x1, y0)), node((x1, y1)), node((x0, y1))]}]
    k = radius * (1 - KAPPA)
    return [{"closed": True, "nodes": [
        node((x0 + radius, y0), i=(x0 + k, y0)),
        node((x1 - radius, y0), o=(x1 - k, y0)),
        node((x1, y0 + radius), i=(x1, y0 + k)),
        node((x1, y1 - radius), o=(x1, y1 - k)),
        node((x1 - radius, y1), i=(x1 - k, y1)),
        node((x0 + radius, y1), o=(x0 + k, y1)),
        node((x0, y1 - radius), i=(x0, y1 - k)),
        node((x0, y0 + radius), o=(x0, y0 + k)),
    ]}]


def ellipse_paths(cx: float, cy: float, rx: float, ry: float) -> list[dict]:
    kx, ky = rx * KAPPA, ry * KAPPA
    return [{"closed": True, "nodes": [
        node((cx, cy - ry), i=(cx - kx, cy - ry), o=(cx + kx, cy - ry)),
        node((cx + rx, cy), i=(cx + rx, cy - ky), o=(cx + rx, cy + ky)),
        node((cx, cy + ry), i=(cx + kx, cy + ry), o=(cx - kx, cy + ry)),
        node((cx - rx, cy), i=(cx - rx, cy + ky), o=(cx - rx, cy - ky)),
    ]}]


def _cubic(p0: Point, c1: Point, c2: Point, p3: Point, t: float) -> Point:
    u = 1 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0], a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1]


def flatten(subpath: Mapping, tolerance: float) -> list[Point]:
    """Convierte el subtrazado en una poligonal (sin repetir el primer punto)."""
    nodes = subpath["nodes"]
    if not nodes:
        return []
    points = [nodes[0]["p"]]
    for p0, c1, c2, p3 in segments(subpath):
        if c1 is None:
            points.append(p3)
            continue
        length = math.dist(p0, c1) + math.dist(c1, c2) + math.dist(c2, p3)
        steps = max(2, min(256, math.ceil(math.sqrt(length / max(tolerance, 1e-6)) * 0.9)))
        points.extend(_cubic(p0, c1, c2, p3, step / steps) for step in range(1, steps + 1))
    if subpath.get("closed") and len(points) > 1 and math.dist(points[0], points[-1]) < 1e-9:
        points.pop()
    return points


def paths_bounds(paths: Sequence[Mapping], tolerance: float = 0.01) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for subpath in paths:
        for x, y in flatten(subpath, tolerance):
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _ring_area(points: Sequence[Point]) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, [*points[1:], points[0]])) / 2


# --------------------------------------------------------------------------- #
# Rasterizado
# --------------------------------------------------------------------------- #

def fill_mask(rings: Iterable[Sequence[Point]], size: tuple[int, int], rule: str = "evenodd") -> Image.Image:
    """Mascara suavizada de anillos cerrados con regla par-impar o de bobinado distinto de cero."""
    width, height = size
    scale = SUPERSAMPLE
    big_w, big_h = width * scale, height * scale
    winding = np.zeros((big_h, big_w), dtype=np.int16)
    for ring in rings:
        if len(ring) < 3:
            continue
        points = [(x * scale, y * scale) for x, y in ring]
        left = max(0, math.floor(min(x for x, _ in points)))
        top = max(0, math.floor(min(y for _, y in points)))
        right = min(big_w, math.ceil(max(x for x, _ in points)) + 1)
        bottom = min(big_h, math.ceil(max(y for _, y in points)) + 1)
        if right <= left or bottom <= top:
            continue
        tile = Image.new("L", (right - left, bottom - top), 0)
        ImageDraw.Draw(tile).polygon([(x - left, y - top) for x, y in points], fill=1)
        sign = 1 if rule == "evenodd" or _ring_area(ring) >= 0 else -1
        winding[top:bottom, left:right] += np.asarray(tile, dtype=np.int16) * sign
    filled = (winding % 2 == 1) if rule == "evenodd" else (winding != 0)
    big = Image.fromarray(filled.astype(np.uint8) * 255)
    return big.resize(size, Image.Resampling.LANCZOS) if scale > 1 else big


def stroke_geometry(
    flat: Sequence[tuple[bool, Sequence[Point]]],
    width: float,
    *,
    cap: str = "butt",
    join: str = "miter",
    dash: str = "solid",
):
    """Superficie del contorno (Shapely) para poligonales abiertas o cerradas."""
    from shapely.geometry import LineString
    from shapely.ops import substring, unary_union

    if width <= 0:
        return None
    cap_style = {"round": "round", "square": "square"}.get(cap, "flat")
    join_style = {"round": "round", "bevel": "bevel"}.get(join, "mitre")
    pattern = [length * width for length in DASH_PATTERNS.get(dash, ())]
    pieces = []
    for closed, points in flat:
        if len(points) < 2:
            continue
        line = LineString([*points, points[0]] if closed else points)
        if line.length <= 0:
            continue
        if not pattern:
            pieces.append(line)
            continue
        position, index = 0.0, 0
        while position < line.length and index < 20000:
            length = pattern[index % len(pattern)]
            if index % 2 == 0:
                piece = substring(line, position, min(line.length, position + length))
                if piece.length > 0:
                    pieces.append(piece)
            position += length
            index += 1
    shapes = [piece.buffer(width / 2, cap_style=cap_style, join_style=join_style, mitre_limit=MITER_LIMIT, quad_segs=8) for piece in pieces]
    shapes = [shape for shape in shapes if not shape.is_empty]
    return unary_union(shapes) if shapes else None


def geometry_rings(geometry) -> list[list[Point]]:
    rings: list[list[Point]] = []
    if geometry is None or geometry.is_empty:
        return rings
    polygons = getattr(geometry, "geoms", [geometry])
    for polygon in polygons:
        if polygon.geom_type != "Polygon":
            rings.extend(geometry_rings(polygon) if hasattr(polygon, "geoms") else [])
            continue
        rings.append(list(polygon.exterior.coords)[:-1])
        rings.extend(list(interior.coords)[:-1] for interior in polygon.interiors)
    return rings


def _hex(value: str | None) -> tuple[int, int, int] | None:
    clean = str(value or "").lstrip("#")
    if len(clean) != 6:
        return None
    try:
        return tuple(int(clean[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None


def paint_image(size: tuple[int, int], gradient: Mapping | None, color: str | None, box: tuple[float, float, float, float] | None = None) -> Image.Image | None:
    """Pintura de relleno: color liso o degradado sobre la caja ``box`` (x, y, ancho, alto) dentro de ``size``."""
    width, height = size
    if gradient:
        start = _hex(gradient.get("start")) or (255, 255, 255)
        end = _hex(gradient.get("end")) or (0, 0, 0)
        bx, by, bw, bh = box or (0, 0, width, height)
        ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
        xs += 0.5
        ys += 0.5
        cx, cy = bx + bw / 2, by + bh / 2
        if gradient.get("kind") == "radial":
            t = np.sqrt(((xs - cx) / max(bw / 2, 1e-6)) ** 2 + ((ys - cy) / max(bh / 2, 1e-6)) ** 2)
        else:
            angle = math.radians(float(gradient.get("angle") or 0))
            dx, dy = math.cos(angle), math.sin(angle)
            extent = abs(bw * dx) + abs(bh * dy)
            t = ((xs - cx) * dx + (ys - cy) * dy) / max(extent, 1e-6) + 0.5
        t = np.clip(t, 0, 1)[..., None]
        rgb = np.asarray(start, np.float32) * (1 - t) + np.asarray(end, np.float32) * t
        alpha = np.full((height, width, 1), 255, np.float32)
        return Image.fromarray(np.concatenate([rgb, alpha], axis=2).round().astype(np.uint8))
    rgb = _hex(color)
    return Image.new("RGBA", size, (*rgb, 255)) if rgb else None


# --------------------------------------------------------------------------- #
# Geometria absoluta (operaciones booleanas)
# --------------------------------------------------------------------------- #

def element_local_paths(element: Mapping, width: float, height: float, radius: float = 0) -> tuple[list[dict], bool]:
    """Subtrazados del objeto en coordenadas locales (origen arriba a la izquierda).

    Devuelve ademas si el objeto es solo linea (sin superficie de relleno).
    """
    kind = element.get("type")
    if kind == "path":
        return scale_paths(normalize_paths(element.get("paths")), width, height), False
    if kind == "ellipse" or (kind == "photo" and element.get("shape") == "circle"):
        return ellipse_paths(width / 2, height / 2, width / 2, height / 2), False
    if kind == "line":
        return [{"closed": False, "nodes": [node((0, height / 2)), node((width, height / 2))]}], True
    return rect_paths(0, 0, width, height, radius if kind in {"rect", "image", "photo", "text"} else 0), False


def rings_geometry(rings: Sequence[Sequence[Point]], rule: str = "evenodd"):
    """Superficie Shapely de anillos con la regla de relleno indicada."""
    from shapely.geometry import Polygon
    from shapely.ops import polygonize, unary_union

    valid = [list(ring) for ring in rings if len(ring) >= 3 and abs(_ring_area(ring)) > 1e-12]
    if not valid:
        return Polygon()
    if len(valid) == 1:
        return Polygon(valid[0]).buffer(0)
    polygons = [Polygon(ring) for ring in valid]
    signs = [1 if _ring_area(ring) >= 0 else -1 for ring in valid]
    boundaries = unary_union([polygon.exterior for polygon in polygons])
    kept = []
    for face in polygonize(boundaries):
        probe = face.representative_point()
        winding = sum(sign for polygon, sign in zip(polygons, signs) if polygon.contains(probe))
        crossings = sum(1 for polygon in polygons if polygon.contains(probe))
        if (rule == "evenodd" and crossings % 2 == 1) or (rule != "evenodd" and winding != 0):
            kept.append(face)
    return unary_union(kept) if kept else Polygon()


def element_geometry(element: Mapping, card_mm: tuple[float, float], tolerance: float = 0.004):
    """Superficie del objeto en milimetros de la tarjeta, con su giro aplicado."""
    from shapely import affinity

    width = float(element.get("w", 0.1)) * card_mm[0]
    height = float(element.get("h", 0.1)) * card_mm[1]
    radius_mm = float(element.get("radius") or 0) * 25.4 / 72
    paths, line_only = element_local_paths(element, width, height, radius_mm)
    if line_only or (element.get("type") == "path" and not element.get("fill") and not element.get("gradient")):
        stroke = max(0.05, float(element.get("stroke_width") or 1) * 25.4 / 72)
        flat = [(subpath["closed"], flatten(subpath, tolerance)) for subpath in paths]
        geometry = stroke_geometry(flat, stroke, cap=str(element.get("line_cap") or "butt"), join=str(element.get("line_join") or "miter"))
    else:
        geometry = rings_geometry([flatten(subpath, tolerance) for subpath in paths], str(element.get("fill_rule") or "evenodd"))
    if geometry is None or geometry.is_empty:
        return geometry
    left = float(element.get("x", 0)) * card_mm[0]
    top = float(element.get("y", 0)) * card_mm[1]
    geometry = affinity.translate(geometry, left, top)
    rotation = float(element.get("rotation") or 0)
    if rotation:
        geometry = affinity.rotate(geometry, rotation, origin=(left + width / 2, top + height / 2))
    return geometry


def boolean_geometry(operation: str, geometries: Sequence):
    from shapely.ops import unary_union

    shapes = [geometry for geometry in geometries if geometry is not None and not geometry.is_empty]
    if len(shapes) < 2:
        raise ValueError("Seleccioná al menos dos formas")
    if operation == "union":
        return unary_union(shapes)
    if operation == "intersection":
        result = shapes[0]
        for shape in shapes[1:]:
            result = result.intersection(shape)
        return result
    if operation == "difference":
        return shapes[0].difference(unary_union(shapes[1:]))
    if operation == "xor":
        result = shapes[0]
        for shape in shapes[1:]:
            result = result.symmetric_difference(shape)
        return result
    raise ValueError("Operación desconocida")


def geometry_paths(geometry, simplify: float = 0.003) -> list[dict]:
    """Anillos de una superficie como subtrazados rectos (en las unidades de la geometria)."""
    if geometry is None or geometry.is_empty:
        return []
    if simplify:
        geometry = geometry.simplify(simplify, preserve_topology=True)
    return [{"closed": True, "nodes": [node((float(x), float(y))) for x, y in ring]} for ring in geometry_rings(geometry) if len(ring) >= 3]


def fit_paths_to_box(paths: Sequence[Mapping], tolerance: float = 0.004) -> tuple[list[dict], tuple[float, float, float, float]] | None:
    """Normaliza trazados absolutos a la caja que los contiene: (trazados 0..1, (x, y, ancho, alto))."""
    bounds = paths_bounds(paths, tolerance)
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    width = max(right - left, 1e-3)
    height = max(bottom - top, 1e-3)
    unit = map_paths(paths, lambda x, y: (round((x - left) / width, 6), round((y - top) / height, 6)))
    return unit, (left, top, width, height)


def serialize_paths(paths: Sequence[Mapping]) -> list[dict]:
    as_list = lambda value: [value[0], value[1]] if value else None  # noqa: E731
    return [
        {"closed": subpath["closed"], "nodes": [{"p": as_list(entry["p"]), "i": as_list(entry.get("i")), "o": as_list(entry.get("o"))} for entry in subpath["nodes"]]}
        for subpath in paths
    ]


# --------------------------------------------------------------------------- #
# Texto a curvas
# --------------------------------------------------------------------------- #

class _OutlinePen:
    """Pluma de fontTools que acumula subtrazados ya transformados."""

    def __init__(self, glyph_set, transform) -> None:
        from fontTools.pens.basePen import BasePen

        outer = self

        class Pen(BasePen):
            def _moveTo(self, point):
                outer.current = {"closed": False, "nodes": [node(transform(*point))]}
                outer.paths.append(outer.current)

            def _lineTo(self, point):
                outer.current["nodes"].append(node(transform(*point)))

            def _curveToOne(self, c1, c2, point):
                nodes = outer.current["nodes"]
                nodes[-1]["o"] = transform(*c1)
                nodes.append(node(transform(*point), i=transform(*c2)))

            def _closePath(self):
                nodes = outer.current["nodes"]
                if len(nodes) > 1 and math.dist(nodes[0]["p"], nodes[-1]["p"]) < 1e-6:
                    nodes[0]["i"] = nodes[-1]["i"]
                    nodes.pop()
                outer.current["closed"] = True

            def _endPath(self):
                pass

        self.paths: list[dict] = []
        self.current: dict | None = None
        self.pen = Pen(glyph_set)


_FONT_CACHE: dict[str, object] = {}


def _tt_font(path: Path):
    from fontTools.ttLib import TTFont

    key = str(path)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = TTFont(str(path), fontNumber=0, lazy=True)
        if len(_FONT_CACHE) > 24:
            _FONT_CACHE.clear()
        _FONT_CACHE[key] = font
    return font


def text_outline(text: str, font_path: Path, size_px: float, origin: Point, pil_font) -> list[dict]:
    """Contornos de una linea de texto con la linea de base en ``origin`` (pixeles, y hacia abajo).

    Las posiciones de cada letra se toman de PIL (``getlength``) para que coincidan
    con el texto rasterizado, incluido el interletrado.
    """
    font = _tt_font(font_path)
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap() or {}
    scale = size_px / float(font["head"].unitsPerEm)
    paths: list[dict] = []
    for index, char in enumerate(text):
        glyph_name = cmap.get(ord(char))
        if glyph_name is None or char.isspace():
            continue
        offset = origin[0] + pil_font.getlength(text[:index])
        pen = _OutlinePen(glyph_set, lambda x, y, offset=offset: (offset + x * scale, origin[1] - y * scale))
        glyph_set[glyph_name].draw(pen.pen)
        paths.extend(subpath for subpath in pen.paths if len(subpath["nodes"]) > 1)
    return paths


# --------------------------------------------------------------------------- #
# Logos SVG
# --------------------------------------------------------------------------- #

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
_UNSUPPORTED_TAGS = {"linearGradient", "radialGradient", "pattern", "filter", "mask", "image", "text", "foreignObject", "clipPath", "script", "switch"}
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_SIMPLE_SELECTOR = re.compile(r"^(?P<tag>[A-Za-z][\w-]*)?(?:#(?P<id>[\w-]+))?(?P<classes>(?:\.[\w-]+)*)$")


def is_svg(content: bytes) -> bool:
    head = content[:2048].lstrip().lower()
    return head.startswith(b"<?xml") and b"<svg" in content[:4096].lower() or head.startswith(b"<svg") or head.startswith(b"<!doctype svg")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _declarations(text: str) -> dict[str, str]:
    result = {}
    for declaration in text.split(";"):
        if ":" in declaration:
            key, value = declaration.split(":", 1)
            if key.strip():
                result[key.strip().lower()] = value.replace("!important", "").strip()
    return result


def svg_for_vector(content: bytes) -> bytes | None:
    """SVG listo para MuPDF: estilos CSS pasados a cada objeto.

    Devuelve None si usa algo que MuPDF no dibuja bien (degradados, mascaras,
    recortes, texto, imagenes o lineas punteadas); en ese caso se usa mapa de bits.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    rules: list[tuple[int, int, str | None, str | None, set[str], dict[str, str]]] = []
    order = 0
    for style in [entry for entry in root.iter() if _local(entry.tag) == "style"]:
        css = re.sub(r"/\*.*?\*/", "", style.text or "", flags=re.S).replace("<![CDATA[", "").replace("]]>", "")
        if "@" in css:
            return None
        for selectors, body in _CSS_RULE.findall(css):
            declarations = _declarations(body)
            for selector in selectors.split(","):
                match = _SIMPLE_SELECTOR.match(selector.strip())
                if not match or not selector.strip():
                    return None
                classes = {name for name in match.group("classes").split(".") if name}
                specificity = (100 if match.group("id") else 0) + 10 * len(classes) + (1 if match.group("tag") else 0)
                rules.append((specificity, order, match.group("tag"), match.group("id"), classes, declarations))
                order += 1
    rules.sort(key=lambda rule: (rule[0], rule[1]))
    parents = {child: parent for parent in root.iter() for child in parent}
    for entry in list(root.iter()):
        tag = _local(entry.tag)
        if tag in _UNSUPPORTED_TAGS:
            return None
        if tag == "style":
            parents[entry].remove(entry)
            continue
        classes = set((entry.get("class") or "").split())
        merged: dict[str, str] = {}
        for _specificity, _order, rule_tag, rule_id, rule_classes, declarations in rules:
            if (rule_tag is None or rule_tag == tag) and (rule_id is None or rule_id == entry.get("id")) and rule_classes <= classes:
                merged.update(declarations)
        merged.update(_declarations(entry.get("style") or ""))
        for key in list(merged):
            if entry.get(key) is not None:
                del entry.attrib[key]
        for key in ("fill", "stroke"):
            value = merged.get(key, entry.get(key) or "")
            if "url(" in value:
                return None
        dash = merged.get("stroke-dasharray", entry.get("stroke-dasharray") or "none")
        if dash.strip() not in {"", "none", "0"}:
            return None
        if merged:
            entry.set("style", ";".join(f"{key}:{value}" for key, value in merged.items()))
        elif "style" in entry.attrib:
            del entry.attrib["style"]
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    return ET.tostring(root, encoding="utf-8")


class SvgAsset:
    """Logo vectorial: se dibuja a la resolucion exacta de salida y se puede llevar al PDF como vector."""

    def __init__(self, content: bytes) -> None:
        import fitz

        self.content = content
        text = content.decode("utf-8", errors="replace")
        self.text = text
        document = fitz.open(stream=content, filetype="svg")
        try:
            rect = document[0].rect
        finally:
            document.close()
        if rect.width <= 0 or rect.height <= 0:
            raise ValueError("El SVG no tiene tamaño")
        self.width = float(rect.width)
        self.height = float(rect.height)
        self._renders: dict[tuple[int, int], Image.Image] = {}
        self._vector: bytes | None | bool = False

    @property
    def size(self) -> tuple[int, int]:
        return max(1, round(self.width)), max(1, round(self.height))

    def render(self, size: tuple[int, int]) -> Image.Image:
        """Mapa de bits RGBA de exactamente ``size`` (estirado si la proporcion no coincide)."""
        size = (max(1, int(size[0])), max(1, int(size[1])))
        cached = self._renders.get(size)
        if cached is not None:
            return cached.copy()
        image = None
        try:
            import resvg_py

            scale = max(size[0] / self.width, size[1] / self.height)
            png = resvg_py.svg_to_bytes(svg_string=self.text, dpi=96.0, width=max(1, round(self.width * scale)))
            image = Image.open(BytesIO(png)).convert("RGBA")
        except Exception:  # noqa: BLE001 - sin resvg se usa MuPDF
            image = None
        if image is None:
            import fitz

            document = fitz.open(stream=self.content, filetype="svg")
            try:
                page = document[0]
                pixmap = page.get_pixmap(matrix=fitz.Matrix(size[0] / page.rect.width, size[1] / page.rect.height), alpha=True)
                image = Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)
            finally:
                document.close()
        if image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        if len(self._renders) > 6:
            self._renders.clear()
        self._renders[size] = image
        return image.copy()

    def vector_pdf(self) -> bytes | None:
        """PDF de una pagina con el logo en vectores, o None si hay que usar mapa de bits."""
        if self._vector is False:
            import fitz

            self._vector = None
            prepared = svg_for_vector(self.content)
            if prepared is not None:
                try:
                    document = fitz.open(stream=prepared, filetype="svg")
                    self._vector = document.convert_to_pdf()
                    document.close()
                except Exception:  # noqa: BLE001
                    self._vector = None
        return self._vector or None


def fit_asset(asset, size: tuple[int, int], mode: str) -> Image.Image:
    """Encaja un recurso (imagen o SVG) en ``size``: cover, contain o stretch."""
    from PIL import ImageOps

    width, height = size
    if isinstance(asset, SvgAsset):
        if mode == "stretch":
            return asset.render(size)
        scale = (max if mode == "cover" else min)(width / asset.width, height / asset.height)
        rendered = asset.render((max(1, round(asset.width * scale)), max(1, round(asset.height * scale))))
        if mode == "cover":
            left = (rendered.width - width) // 2
            top = (rendered.height - height) // 2
            return rendered.crop((left, top, left + width, top + height))
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        layer.alpha_composite(rendered, ((width - rendered.width) // 2, (height - rendered.height) // 2))
        return layer
    source = asset.convert("RGBA")
    if mode == "stretch":
        return source.resize(size, Image.Resampling.LANCZOS)
    if mode == "contain":
        fitted = ImageOps.contain(source, size, Image.Resampling.LANCZOS)
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        layer.alpha_composite(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
        return layer
    return ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
