import io
import sys
import unittest
from pathlib import Path

import fitz
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import card_vectors as vectors
from card_renderer import CardRenderer, record_values
from card_vector_pdf import convert_to_paths, side_pdf
from test_card_designer import CardSessionCase, design

COREL_SVG = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" width="40mm" height="20mm" viewBox="0 0 4000 2000">
 <defs><style type="text/css"><![CDATA[ .fil0 {fill:#E30613} .fil1 {fill:#1D71B8} ]]></style></defs>
 <g><rect class="fil0" width="2000" height="2000"/><circle class="fil1" cx="3000" cy="1000" r="900"/></g>
</svg>"""
GRADIENT_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">
<defs><linearGradient id="g"><stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff"/></linearGradient></defs>
<rect width="100" height="50" fill="url(#g)"/></svg>"""

SQUARE = [{"closed": True, "nodes": [{"p": [0, 0]}, {"p": [1, 0]}, {"p": [1, 1]}, {"p": [0, 1]}]}]
INNER = {"closed": True, "nodes": [{"p": [0.25, 0.25]}, {"p": [0.75, 0.25]}, {"p": [0.75, 0.75]}, {"p": [0.25, 0.75]}]}


def card(elements, background="#ffffff"):
    return {"background_color": background, "elements": elements}


class VectorRasterTests(unittest.TestCase):
    def setUp(self):
        self.renderer = CardRenderer(width_mm=50, height_mm=50, dpi=100)

    def test_path_fill_rules_and_bezier_handles(self):
        # Mismo sentido de giro en ambos anillos: par-impar deja hueco, distinto de cero no.
        element = {"id": "p", "type": "path", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8, "fill": "#ff0000", "paths": [SQUARE[0], INNER]}
        evenodd = self.renderer.render_side(card([element]), {}, None)
        nonzero = self.renderer.render_side(card([{**element, "fill_rule": "nonzero"}]), {}, None)
        self.assertEqual(evenodd.getpixel((98, 98)), (255, 255, 255))
        self.assertEqual(evenodd.getpixel((40, 40)), (255, 0, 0))
        self.assertEqual(nonzero.getpixel((98, 98)), (255, 0, 0))
        curve = {"id": "c", "type": "path", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#0000ff", "paths": [{"closed": True, "nodes": [
            {"p": [0, 1], "o": [0, 0]}, {"p": [1, 1], "i": [1, 0]},
        ]}]}
        image = self.renderer.render_side(card([curve]), {}, None)
        self.assertEqual(image.getpixel((98, 150)), (0, 0, 255))
        self.assertEqual(image.getpixel((5, 60)), (255, 255, 255))

    def test_gradient_dash_and_round_caps(self):
        rect = {"id": "g", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#000000",
                "gradient": {"kind": "linear", "start": "#ff0000", "end": "#0000ff", "angle": 0}}
        image = self.renderer.render_side(card([rect]), {}, None)
        left, right = image.getpixel((2, 98)), image.getpixel((194, 98))
        self.assertGreater(left[0], 240)
        self.assertGreater(right[2], 240)
        radial = self.renderer.render_side(card([{**rect, "gradient": {"kind": "radial", "start": "#ffffff", "end": "#000000"}}]), {}, None)
        self.assertGreater(radial.getpixel((98, 98))[0], 240)
        self.assertLess(radial.getpixel((2, 98))[0], 15)
        line = {"id": "l", "type": "line", "x": 0.1, "y": 0.45, "w": 0.8, "h": 0.1, "stroke_color": "#000000", "stroke_width": 6, "dash": "dash"}
        image = self.renderer.render_side(card([line]), {}, None).convert("L")
        row = [image.getpixel((x, 98)) for x in range(20, 177)]
        self.assertTrue(any(value < 60 for value in row) and any(value > 200 for value in row))
        round_cap = self.renderer.render_side(card([{**line, "dash": "solid", "line_cap": "round"}]), {}, None).convert("L")
        self.assertLess(round_cap.getpixel((16, 98)), 100)
        butt = self.renderer.render_side(card([{**line, "dash": "solid"}]), {}, None).convert("L")
        self.assertGreater(butt.getpixel((16, 98)), 200)

    def test_svg_logo_css_and_recolor(self):
        asset = vectors.SvgAsset(COREL_SVG)
        renderer = CardRenderer(width_mm=50, height_mm=50, dpi=100, assets={"logo": asset})
        logo = {"id": "i", "type": "image", "x": 0, "y": 0, "w": 1, "h": 0.5, "asset": "logo", "image_fit": "contain"}
        image = renderer.render_side(card([logo]), {}, None)
        self.assertEqual(image.getpixel((40, 50))[:3], (227, 6, 19))
        self.assertEqual(image.getpixel((148, 50))[:3], (29, 113, 184))
        tinted = renderer.render_side(card([{**logo, "recolor": "#00aa00"}], "#000000"), {}, None)
        self.assertEqual(tinted.getpixel((40, 50)), (0, 170, 0))
        self.assertEqual(tinted.getpixel((98, 150)), (0, 0, 0))
        prepared = vectors.svg_for_vector(COREL_SVG)
        self.assertIn(b"fill:#E30613", prepared)
        self.assertNotIn(b"<style", prepared)
        self.assertIsNone(vectors.svg_for_vector(GRADIENT_SVG))


class VectorPdfTests(unittest.TestCase):
    def test_vector_side_matches_raster_and_has_no_fonts(self):
        renderer = CardRenderer(width_mm=85.6, height_mm=53.98, dpi=300, assets={"logo": vectors.SvgAsset(COREL_SVG)})
        side = {"background_color": "#f4f7fb", "elements": [
            {"id": "t", "type": "text", "x": 0.05, "y": 0.05, "w": 0.6, "h": 0.15, "text": "Hola {Nombre}", "size": 14, "bold": True, "underline": True},
            {"id": "s", "type": "path", "x": 0.05, "y": 0.3, "w": 0.2, "h": 0.3, "rotation": 20, "fill": "#f2b705", "stroke_color": "#17202b", "stroke_width": 1, "paths": SQUARE},
            {"id": "q", "type": "qr", "x": 0.7, "y": 0.5, "w": 0.2, "h": 0.35, "value": "{Nombre}", "background": "#ffffff"},
            {"id": "b", "type": "barcode", "x": 0.3, "y": 0.7, "w": 0.35, "h": 0.25, "value": "12345"},
            {"id": "i", "type": "image", "x": 0.7, "y": 0.1, "w": 0.25, "h": 0.2, "asset": "logo", "image_fit": "contain"},
            {"id": "e", "type": "ellipse", "x": 0.3, "y": 0.3, "w": 0.2, "h": 0.3, "fill": None, "stroke_color": "#176b87", "stroke_width": 2, "dash": "dot"},
        ]}
        values = record_values({"Nombre": "Ana"}, "ana.jpg", 1)
        document = side_pdf(renderer, side, values, None)
        page = document[0]
        self.assertEqual(page.get_fonts(), [])
        self.assertEqual(page.get_images(), [])
        self.assertGreater(len(page.get_drawings()), 5)
        pixmap = page.get_pixmap(dpi=300)
        vector = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples).resize(renderer.size)
        raster = renderer.render_side(side, values, None)
        difference = sum(abs(a - b) for a, b in zip(vector.convert("L").tobytes(), raster.convert("L").tobytes())) / (renderer.size[0] * renderer.size[1])
        self.assertLess(difference, 6)

    def test_convert_to_paths_keeps_rotated_position(self):
        renderer = CardRenderer(width_mm=100, height_mm=50, dpi=300)
        rect = {"id": "r", "type": "rect", "x": 0.2, "y": 0.2, "w": 0.3, "h": 0.4, "rotation": 30, "fill": "#ff0000", "stroke_color": "#000000", "stroke_width": 2}
        converted = convert_to_paths(renderer, rect, {})
        self.assertEqual(len(converted), 2)
        shape = converted[0]
        self.assertAlmostEqual(shape["x"] + shape["w"] / 2, 0.35, places=3)
        self.assertAlmostEqual(shape["y"] + shape["h"] / 2, 0.4, places=3)
        self.assertEqual(shape["rotation"], 30)
        before = renderer.render_side(card([rect]), {}, None)
        after = renderer.render_side(card([{**entry, "id": f"p{index}"} for index, entry in enumerate(converted)]), {}, None)
        difference = sum(abs(a - b) for a, b in zip(before.convert("L").tobytes(), after.convert("L").tobytes())) / (before.width * before.height)
        self.assertLess(difference, 2)


class VectorEndpointTests(CardSessionCase):
    def upload_asset(self, name, content, content_type="image/svg+xml"):
        return self.client.post(
            f"/api/photo-crop/sessions/{self.session_id}/assets", params={"filename": name},
            content=content, headers={"Content-Type": content_type},
        )

    def test_svg_asset_upload_and_safe_serving(self):
        response = self.upload_asset("logo.svg", COREL_SVG)
        self.assertEqual(response.status_code, 201, response.text)
        served = self.client.get(response.json()["url"])
        self.assertEqual(served.headers["content-type"], "image/svg+xml")
        self.assertIn("sandbox", served.headers["content-security-policy"])
        self.assertEqual(self.upload_asset("roto.svg", b"<svg><rect").status_code, 415)
        self.assertEqual(self.upload_asset("texto.svg", b"hola").status_code, 415)
        legacy = self.client.post(
            f"/api/photo-crop/sessions/{self.session_id}/logo", params={"filename": "logo.svg"},
            content=COREL_SVG, headers={"Content-Type": "image/svg+xml"},
        )
        self.assertEqual(legacy.status_code, 415)

    def test_vector_and_raster_pdf_export(self):
        asset_id = self.upload_asset("logo.svg", COREL_SVG).json()["asset_id"]
        card_design = design()
        card_design["front"]["elements"].append({"id": "logo", "type": "image", "x": 0.75, "y": 0.02, "w": 0.2, "h": 0.15, "asset": asset_id})
        card_design["front"]["elements"].append({"id": "estrella", "type": "path", "x": 0.85, "y": 0.6, "w": 0.1, "h": 0.15, "fill": "#ff0000", "paths": SQUARE})
        url = f"/api/photo-crop/sessions/{self.session_id}/cards/export"
        vector = self.client.post(url, json={"design": card_design, "items": self.items()[:1], "output": {"format": "PDF"}})
        self.assertEqual(vector.status_code, 200, vector.text)
        page = fitz.open("pdf", vector.content)[0]
        self.assertEqual(len(page.get_images()), 1)  # sólo la foto
        self.assertEqual(page.get_fonts(), [])
        self.assertGreater(len(page.get_drawings()), 3)
        raster = self.client.post(url, json={"design": card_design, "items": self.items()[:1], "output": {"format": "PDF", "vector": False}})
        page = fitz.open("pdf", raster.content)[0]
        self.assertEqual(len(page.get_images()), 1)
        self.assertEqual(len(page.get_drawings()), 0)
        sheet = self.client.post(url, json={"design": card_design, "items": self.items(), "output": {"format": "PDF", "pdf_layout": "sheet"}})
        self.assertEqual(sheet.status_code, 200, sheet.text)
        self.assertEqual(fitz.open("pdf", sheet.content).page_count, 1)

    def test_outline_and_boolean_operations(self):
        base = {"width_mm": 100, "height_mm": 50, "values": {"Nombre": "Ana"}}
        text = {"id": "t", "type": "text", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.3, "text": "Hola {Nombre}", "color": "#112233"}
        response = self.client.post("/api/photo-crop/vector/outline", json={**base, "elements": [text]})
        self.assertEqual(response.status_code, 200, response.text)
        converted = response.json()["results"][0]["elements"]
        self.assertEqual(converted[0]["type"], "path")
        self.assertEqual(converted[0]["fill"], "#112233")
        self.assertEqual(converted[0]["fill_rule"], "nonzero")
        self.assertGreater(len(converted[0]["paths"]), 5)

        left = {"id": "a", "type": "rect", "x": 0.1, "y": 0.2, "w": 0.4, "h": 0.4, "fill": "#ff0000"}
        right = {"id": "b", "type": "ellipse", "x": 0.3, "y": 0.2, "w": 0.4, "h": 0.4, "fill": "#00ff00"}
        far = {"id": "c", "type": "rect", "x": 0.8, "y": 0.8, "w": 0.1, "h": 0.1, "fill": "#0000ff"}
        url = "/api/photo-crop/vector/boolean"
        union = self.client.post(url, json={**base, "operation": "union", "elements": [left, right]}).json()["element"]
        self.assertAlmostEqual(union["x"], 0.1, places=3)
        self.assertAlmostEqual(union["x"] + union["w"], 0.7, places=3)
        difference = self.client.post(url, json={**base, "operation": "difference", "elements": [left, right]}).json()["element"]
        self.assertAlmostEqual(difference["x"] + difference["w"], 0.5, places=3)
        intersection = self.client.post(url, json={**base, "operation": "intersection", "elements": [left, right]}).json()["element"]
        self.assertAlmostEqual(intersection["x"], 0.3, places=3)
        empty = self.client.post(url, json={**base, "operation": "intersection", "elements": [left, far]})
        self.assertEqual(empty.status_code, 422)
        photo = {"id": "f", "type": "photo", "x": 0, "y": 0, "w": 0.2, "h": 0.2}
        self.assertEqual(self.client.post(url, json={**base, "operation": "union", "elements": [left, photo]}).status_code, 422)
        cut_text = self.client.post(url, json={**base, "operation": "difference", "elements": [
            {**left, "w": 0.8, "x": 0.05, "y": 0.05, "h": 0.5}, text,
        ]})
        self.assertEqual(cut_text.status_code, 200, cut_text.text)
        self.assertGreater(len(cut_text.json()["element"]["paths"]), 5)


if __name__ == "__main__":
    unittest.main()
