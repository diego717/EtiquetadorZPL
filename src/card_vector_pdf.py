"""Salida vectorial de las credenciales y conversion de objetos a curvas.

El PDF vectorial dibuja formas, trazados, textos (pasados a curvas), codigos QR,
codigos de barras y logos SVG como vectores, de modo que una imprenta puede
ampliarlos sin perder calidad. Lo que no tiene equivalente vectorial (fotos,
imagenes de mapa de bits, degradados) se inserta como imagen a la resolucion
elegida, con el mismo motor que la salida en mapa de bits.
"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Mapping, Sequence

from PIL import Image

import card_vectors as vectors
from card_renderer import (
    BarcodeError,
    CardRenderer,
    _rgb,
    barcode_modules,
    condition_matches,
    inset_shape_paths,
    qr_matrix,
    resolve_fields,
    _bar_runs,
)

CAPS = {"butt": 0, "round": 1, "square": 2}
JOINS = {"miter": 0, "round": 1, "bevel": 2}


class NotVector(Exception):
    """El objeto no se puede expresar en vectores; se usa su imagen."""


# --------------------------------------------------------------------------- #
# Capas de pintura de un objeto (en pixeles locales de la caja)
# --------------------------------------------------------------------------- #

def _paint(paths, *, fill=None, gradient=None, stroke=None, width=0.0, rule="evenodd", cap="butt", join="miter", dash="solid") -> dict:
    return {"paths": paths, "fill": fill, "gradient": gradient, "stroke": stroke, "width": width, "rule": rule, "cap": cap, "join": join, "dash": dash}


def _rect_run_paths(rects: Sequence[tuple[float, float, float, float]]) -> list[dict]:
    return [vectors.rect_paths(left, top, right, bottom)[0] for left, top, right, bottom in rects if right > left and bottom > top]


def _text_paths(renderer: CardRenderer, font, family: str, bold: bool, italic: bool, lines) -> list[dict]:
    path = renderer.fonts.path(family, bold, italic)
    if path is None:
        raise NotVector("tipografía sin archivo")
    ascent, descent = font.getmetrics()
    paths: list[dict] = []
    try:
        for line, x, y, _width in lines:
            if line.strip():
                paths.extend(vectors.text_outline(line, path, font.size, (x, y + (ascent - descent) / 2), font))
    except Exception as exc:  # noqa: BLE001 - fuentes que fontTools no puede leer
        raise NotVector(str(exc)) from exc
    return paths


def element_paints(renderer: CardRenderer, element: Mapping, values: Mapping[str, str], size: tuple[float, float]) -> list[dict]:
    """Pinturas vectoriales del objeto, de abajo hacia arriba. Lanza NotVector si no corresponde."""
    kind = element.get("type")
    width, height = size
    stroke = element.get("stroke_color") or None
    stroke_px = renderer.pt(element.get("stroke_width", 0)) if stroke else 0
    style = {"cap": str(element.get("line_cap") or "butt"), "join": str(element.get("line_join") or "miter"), "dash": str(element.get("dash") or "solid")}
    if kind in {"rect", "ellipse"}:
        shape = "ellipse" if kind == "ellipse" else "rect"
        radius = renderer.pt(element.get("radius", 0)) if shape == "rect" else 0
        paints = []
        if element.get("fill") or element.get("gradient"):
            outline = vectors.ellipse_paths(width / 2, height / 2, width / 2, height / 2) if shape == "ellipse" else vectors.rect_paths(0, 0, width, height, radius)
            paints.append(_paint(outline, fill=element.get("fill"), gradient=element.get("gradient")))
        if stroke and stroke_px > 0:
            paints.append(_paint(inset_shape_paths(shape, size, radius, stroke_px), stroke=stroke, width=stroke_px, **style))
        return paints
    if kind == "path":
        paths = vectors.scale_paths(vectors.normalize_paths(element.get("paths")), width, height)
        return [_paint(paths, fill=element.get("fill"), gradient=element.get("gradient"), stroke=stroke, width=stroke_px, rule=str(element.get("fill_rule") or "evenodd"), **style)] if paths else []
    if kind == "line":
        paths = [{"closed": False, "nodes": [vectors.node((0, height / 2)), vectors.node((width, height / 2))]}]
        return [_paint(paths, stroke=stroke or "#17202b", width=max(1.0, renderer.pt(element.get("stroke_width", 1) or 1)), **style)]
    if kind == "text":
        paints = []
        if element.get("fill"):
            paints.append(_paint(vectors.rect_paths(0, 0, width, height, renderer.pt(element.get("radius", 0))), fill=element.get("fill")))
        placement = renderer.text_lines(element, (max(1, round(width)), max(1, round(height))), values)
        if placement is None:
            return paints
        font, lines = placement
        glyphs = _text_paths(renderer, font, str(element.get("font") or "sans"), bool(element.get("bold")), bool(element.get("italic")), lines)
        if element.get("underline"):
            glyphs.extend(_rect_run_paths([renderer.underline_box(font, x, y, line_width) for line, x, y, line_width in lines if line]))
        color = element.get("color") or "#17202b"
        text_stroke = round(renderer.pt(element.get("stroke_width", 0))) if stroke else 0
        if text_stroke:
            paints.append(_paint(glyphs, stroke=stroke, width=text_stroke * 2, join="round", cap="round", rule="nonzero"))
        paints.append(_paint(glyphs, fill=color, rule="nonzero"))
        return paints
    if kind == "qr":
        value = resolve_fields(str(element.get("value") or ""), values).strip()
        if not value:
            return []
        matrix = qr_matrix(value, str(element.get("ecc") or "M"))
        modules = len(matrix)
        module_px = max(1, int(min(size)) // modules)
        code_px = module_px * modules
        left, top = (int(width) - code_px) // 2, (int(height) - code_px) // 2
        paints = []
        if element.get("background"):
            paints.append(_paint(vectors.rect_paths(left, top, left + code_px, top + code_px), fill=element.get("background")))
        rects = []
        for row_index, row in enumerate(matrix):
            column = 0
            while column < modules:
                if not row[column]:
                    column += 1
                    continue
                start = column
                while column < modules and row[column]:
                    column += 1
                y = top + row_index * module_px
                rects.append((left + start * module_px, y, left + column * module_px, y + module_px))
        paints.append(_paint(_rect_run_paths(rects), fill=element.get("color") or "#000000", rule="nonzero"))
        return paints
    if kind == "barcode":
        value = resolve_fields(str(element.get("value") or ""), values).strip()
        if not value:
            return []
        try:
            modules, readable = barcode_modules(str(element.get("symbology") or "code128"), value)
        except BarcodeError as exc:
            raise NotVector("código inválido") from exc
        paints = []
        if element.get("background"):
            paints.append(_paint(vectors.rect_paths(0, 0, width, height), fill=element.get("background")))
        show_text = bool(element.get("show_text", True))
        text_height = round(height * 0.22) if show_text else 0
        bar_height = max(1, round(height) - text_height)
        count = len(modules)
        module_px = width / count
        if module_px >= 1:
            module_px = math.floor(module_px)
        start_x = (width - module_px * count) / 2
        rects = [(round(start_x + start * module_px), 0, max(round(start_x + start * module_px) + 1, round(start_x + (start + length) * module_px)), bar_height) for start, length in _bar_runs(modules)]
        shapes = _rect_run_paths(rects)
        if show_text:
            font = renderer.fonts.get("sans", False, False, max(6, round(text_height * 0.9)))
            text_width = font.getlength(readable)
            shapes.extend(_text_paths(renderer, font, "sans", False, False, [(readable, width / 2 - text_width / 2, bar_height + text_height / 2, text_width)]))
        paints.append(_paint(shapes, fill=element.get("color") or "#000000", rule="nonzero"))
        return paints
    raise NotVector(str(kind))


# --------------------------------------------------------------------------- #
# Convertir a curvas
# --------------------------------------------------------------------------- #

def _placement(renderer: CardRenderer, element: Mapping) -> tuple[float, float, float, float, float]:
    # Mismo redondeo que la capa en mapa de bits, para que ambas salidas coincidan.
    width = float(max(1, round(float(element.get("w", 0.1)) * renderer.size[0])))
    height = float(max(1, round(float(element.get("h", 0.1)) * renderer.size[1])))
    center_x = (float(element.get("x", 0)) + float(element.get("w", 0)) / 2) * renderer.size[0]
    center_y = (float(element.get("y", 0)) + float(element.get("h", 0)) / 2) * renderer.size[1]
    return width, height, center_x, center_y, float(element.get("rotation") or 0)


def convert_to_paths(renderer: CardRenderer, element: Mapping, values: Mapping[str, str]) -> list[dict]:
    """Objetos ``path`` equivalentes (uno por pintura), con la misma posicion y giro."""
    width, height, center_x, center_y, rotation = _placement(renderer, element)
    paints = element_paints(renderer, element, values, (width, height))
    angle = math.radians(rotation)
    cos, sin = math.cos(angle), math.sin(angle)
    keep = {key: element[key] for key in ("opacity", "hidden", "locked", "condition") if element.get(key) is not None}
    result = []
    for index, paint in enumerate(paints):
        fitted = vectors.fit_paths_to_box(paint["paths"], 0.25)
        if fitted is None:
            continue
        unit, (left, top, box_w, box_h) = fitted
        offset_x = left + box_w / 2 - width / 2
        offset_y = top + box_h / 2 - height / 2
        new_cx = center_x + offset_x * cos - offset_y * sin
        new_cy = center_y + offset_x * sin + offset_y * cos
        result.append({
            **keep,
            "type": "path",
            "name": (element.get("name") or "") + ("" if len(paints) == 1 else f" {index + 1}"),
            "x": (new_cx - box_w / 2) / renderer.size[0],
            "y": (new_cy - box_h / 2) / renderer.size[1],
            "w": box_w / renderer.size[0],
            "h": box_h / renderer.size[1],
            "rotation": rotation,
            "paths": vectors.serialize_paths(unit),
            "fill": paint["fill"],
            "gradient": paint["gradient"],
            "fill_rule": paint["rule"],
            "stroke_color": paint["stroke"],
            "stroke_width": round(paint["width"] * 72 / renderer.dpi, 3),
            "line_cap": paint["cap"],
            "line_join": paint["join"],
            "dash": paint["dash"],
        })
    return result


def element_area(renderer: CardRenderer, element: Mapping, values: Mapping[str, str], card_mm: tuple[float, float]):
    """Superficie Shapely del objeto en milimetros (para soldar, recortar e intersectar)."""
    from shapely import affinity
    from shapely.ops import unary_union

    if element.get("type") in {"rect", "ellipse", "path", "line"}:
        return vectors.element_geometry(element, card_mm)
    width, height, center_x, center_y, rotation = _placement(renderer, element)
    shapes = []
    for paint in element_paints(renderer, element, values, (width, height)):
        if paint["fill"] or paint["gradient"]:
            shapes.append(vectors.rings_geometry([vectors.flatten(subpath, 0.2) for subpath in paint["paths"]], paint["rule"]))
    if not shapes:
        return None
    geometry = unary_union(shapes)
    to_mm = 25.4 / renderer.dpi
    geometry = affinity.translate(geometry, center_x - width / 2, center_y - height / 2)
    if rotation:
        geometry = affinity.rotate(geometry, rotation, origin=(center_x, center_y))
    return affinity.scale(geometry, to_mm, to_mm, origin=(0, 0))


# --------------------------------------------------------------------------- #
# PDF vectorial
# --------------------------------------------------------------------------- #

def _color(value) -> tuple[float, float, float] | None:
    rgb = _rgb(value)
    return tuple(channel / 255 for channel in rgb) if rgb else None


def _draw_paths(page, paths, transform, *, fill=None, stroke=None, width=0.0, rule="evenodd", cap="butt", join="miter", dash="solid", opacity=1.0) -> None:
    shape = page.new_shape()
    drawn = False
    for subpath in paths:
        if len(subpath["nodes"]) < 2:
            continue
        for p0, c1, c2, p3 in vectors.segments(subpath):
            if c1 is None:
                shape.draw_line(transform(*p0), transform(*p3))
            else:
                shape.draw_bezier(transform(*p0), transform(*c1), transform(*c2), transform(*p3))
            drawn = True
        if subpath["closed"]:
            shape.draw_cont += "h\n"
    if not drawn:
        return
    pattern = vectors.DASH_PATTERNS.get(dash)
    dashes = "[" + " ".join(f"{length * width:.3f}" for length in pattern) + "] 0" if pattern and stroke else None
    shape.finish(
        color=_color(stroke) if stroke and width > 0 else None,
        fill=_color(fill) if fill else None,
        width=width if stroke else 0,
        lineCap=CAPS.get(cap, 0),
        lineJoin=JOINS.get(join, 0),
        dashes=dashes,
        even_odd=rule == "evenodd",
        closePath=False,
        fill_opacity=opacity,
        stroke_opacity=opacity,
    )
    shape.commit()


def _image_bytes(layer: Image.Image) -> bytes:
    output = BytesIO()
    if layer.mode == "RGBA" and layer.getchannel("A").getextrema() != (255, 255):
        layer.save(output, "PNG", compress_level=6)
    else:
        layer.convert("RGB").save(output, "JPEG", quality=95, subsampling=0)
    return output.getvalue()


def _raster(page, renderer: CardRenderer, element: Mapping, values: Mapping[str, str], portrait) -> None:
    import fitz

    placed = renderer.element_layer(element, values, portrait)
    if placed is None:
        return
    layer, left, top = placed
    scale = 72 / renderer.dpi
    page.insert_image(fitz.Rect(left * scale, top * scale, (left + layer.width) * scale, (top + layer.height) * scale), stream=_image_bytes(layer))


def _cover_clip(source_rect, target_w: float, target_h: float):
    import fitz

    ratio = target_w / target_h
    if source_rect.width / source_rect.height > ratio:
        clip_w = source_rect.height * ratio
        left = source_rect.x0 + (source_rect.width - clip_w) / 2
        return fitz.Rect(left, source_rect.y0, left + clip_w, source_rect.y1)
    clip_h = source_rect.width / ratio
    top = source_rect.y0 + (source_rect.height - clip_h) / 2
    return fitz.Rect(source_rect.x0, top, source_rect.x1, top + clip_h)


def _show_svg(page, asset: vectors.SvgAsset, rect, mode: str) -> bool:
    import fitz

    pdf = asset.vector_pdf()
    if not pdf:
        return False
    source = fitz.open("pdf", pdf)
    try:
        if mode == "cover":
            page.show_pdf_page(rect, source, 0, clip=_cover_clip(source[0].rect, rect.width, rect.height))
        else:
            page.show_pdf_page(rect, source, 0, keep_proportion=mode != "stretch")
    finally:
        source.close()
    return True


def _vector_image(page, renderer: CardRenderer, element: Mapping, transform) -> bool:
    import fitz

    asset = renderer.assets.get(str(element.get("asset") or ""))
    if not isinstance(asset, vectors.SvgAsset):
        return False
    if element.get("recolor") or element.get("grayscale") or float(element.get("rotation") or 0) % 360 or float(element.get("opacity", 1)) < 0.999 or float(element.get("radius") or 0) > 0:
        return False
    width, height, center_x, center_y, _rotation = _placement(renderer, element)
    scale = 72 / renderer.dpi
    rect = fitz.Rect((center_x - width / 2) * scale, (center_y - height / 2) * scale, (center_x + width / 2) * scale, (center_y + height / 2) * scale)
    if not _show_svg(page, asset, rect, str(element.get("image_fit") or "contain")):
        return False
    stroke = element.get("stroke_color")
    stroke_px = renderer.pt(element.get("stroke_width", 0))
    if stroke and stroke_px > 0:
        _draw_paths(page, inset_shape_paths("rect", (width, height), 0, stroke_px), transform, stroke=stroke, width=stroke_px * scale)
    return True


def side_pdf(renderer: CardRenderer, side: Mapping, values: Mapping[str, str], portrait):
    """Documento de una pagina, del tamaño exacto de la tarjeta, con la cara en vectores."""
    import fitz

    scale = 72 / renderer.dpi
    page_w, page_h = renderer.size[0] * scale, renderer.size[1] * scale
    document = fitz.open()
    page = document.new_page(width=page_w, height=page_h)
    page.draw_rect(page.rect, color=None, fill=_color(side.get("background_color")) or (1, 1, 1), width=0)
    image_id = side.get("background_image")
    if image_id and image_id in renderer.assets:
        asset = renderer.assets[image_id]
        if not (isinstance(asset, vectors.SvgAsset) and _show_svg(page, asset, page.rect, "cover")):
            page.insert_image(page.rect, stream=_image_bytes(vectors.fit_asset(asset, renderer.size, "cover").convert("RGB")))
    for element in side.get("elements") or []:
        if element.get("hidden") or not condition_matches(element.get("condition"), values):
            continue
        width, height, center_x, center_y, rotation = _placement(renderer, element)
        angle = math.radians(rotation)
        cos, sin = math.cos(angle), math.sin(angle)

        def transform(x, y, width=width, height=height, center_x=center_x, center_y=center_y, cos=cos, sin=sin):
            dx, dy = x - width / 2, y - height / 2
            return fitz.Point((center_x + dx * cos - dy * sin) * scale, (center_y + dx * sin + dy * cos) * scale)

        kind = element.get("type")
        if kind == "image":
            if not _vector_image(page, renderer, element, transform):
                _raster(page, renderer, element, values, portrait)
            continue
        if kind == "photo":
            _raster(page, renderer, element, values, portrait)
            continue
        try:
            paints = element_paints(renderer, element, values, (width, height))
        except NotVector:
            _raster(page, renderer, element, values, portrait)
            continue
        if any(paint["gradient"] for paint in paints):
            _raster(page, renderer, element, values, portrait)
            continue
        opacity = max(0.0, min(1.0, float(element.get("opacity", 1))))
        for paint in paints:
            _draw_paths(
                page, paint["paths"], transform, fill=paint["fill"], stroke=paint["stroke"], width=paint["width"] * scale,
                rule=paint["rule"], cap=paint["cap"], join=paint["join"], dash=paint["dash"], opacity=opacity,
            )
    return document
