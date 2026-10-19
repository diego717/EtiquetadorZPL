import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import photo_crop_endpoints
from card_renderer import (
    CardRenderer,
    barcode_modules,
    BarcodeError,
    condition_matches,
    record_values,
    resolve_fields,
    sheet_grid,
)


def image_bytes(size=(640, 900), color=(105, 145, 185), format_name="JPEG"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format_name)
    return output.getvalue()


def design(double_sided=False, back_elements=None):
    return {
        "width_mm": 85.6,
        "height_mm": 53.98,
        "double_sided": double_sided,
        "front": {
            "background_color": "#ffffff",
            "elements": [
                {"id": "banda", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 0.2, "fill": "#176b87"},
                {"id": "foto", "type": "photo", "x": 0.05, "y": 0.25, "w": 0.3, "h": 0.7, "radius": 4},
                {"id": "nombre", "type": "text", "x": 0.4, "y": 0.3, "w": 0.55, "h": 0.15,
                 "text": "{Nombre} {Apellido}", "size": 14, "bold": True},
                {"id": "codigo", "type": "barcode", "x": 0.4, "y": 0.6, "w": 0.4, "h": 0.3, "value": "{Legajo}"},
            ],
        },
        "back": {"background_color": "#eeeeee", "elements": back_elements or [
            {"id": "aviso", "type": "text", "x": 0.05, "y": 0.4, "w": 0.9, "h": 0.2, "text": "Dorso {Nro}"},
        ]},
    }


class CardRendererTests(unittest.TestCase):
    def test_fields_and_conditions(self):
        values = record_values({"Nombre": "Ana", "Cargo": "Ventas"}, "ana_perez.jpg", 7)
        self.assertEqual(resolve_fields("{Nombre} · {Archivo} · {Nro} · {Desconocido}", values), "Ana · ana_perez · 7 · ")
        self.assertTrue(condition_matches({"field": "Cargo", "op": "equals", "value": "ventas"}, values))
        self.assertFalse(condition_matches({"field": "Cargo", "op": "empty"}, values))
        self.assertTrue(condition_matches({"field": "Turno", "op": "empty"}, values))
        self.assertTrue(condition_matches(None, values))

    def test_hidden_and_conditional_elements_are_skipped(self):
        renderer = CardRenderer(width_mm=50, height_mm=50, dpi=100)
        side = {"background_color": "#ffffff", "elements": [
            {"id": "a", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#ff0000",
             "condition": {"field": "Cargo", "op": "equals", "value": "Gerencia"}},
            {"id": "b", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#00ff00", "hidden": True},
        ]}
        image = renderer.render_side(side, {"Cargo": "Ventas"}, None)
        self.assertEqual(image.getpixel((50, 50)), (255, 255, 255))
        image = renderer.render_side(side, {"Cargo": "Gerencia"}, None)
        self.assertEqual(image.getpixel((50, 50)), (255, 0, 0))

    def test_size_scales_with_dpi_and_rotation_keeps_center(self):
        side = {"elements": [{"id": "r", "type": "rect", "x": 0.4, "y": 0.4, "w": 0.2, "h": 0.2, "fill": "#000000", "rotation": 45}]}
        low = CardRenderer(width_mm=85.6, height_mm=53.98, dpi=300).render_side(side, {}, None)
        high = CardRenderer(width_mm=85.6, height_mm=53.98, dpi=600).render_side(side, {}, None)
        self.assertEqual(low.size, (1011, 638))
        self.assertEqual(high.size, (2022, 1275))
        self.assertEqual(low.getpixel((505, 319)), (0, 0, 0))

    def test_invalid_barcode_is_reported(self):
        self.assertTrue(barcode_modules("code128", "A-100")[0].startswith("1"))
        with self.assertRaises(BarcodeError):
            barcode_modules("ean13", "ABC")

    def test_sheet_grid_rotates_page_when_more_cards_fit(self):
        self.assertEqual(sheet_grid((85.6, 53.98), (210, 297), 10, 4), (3, 3, True))
        self.assertEqual(sheet_grid((85.6, 53.98), (210, 297), 5, 0), (2, 5, False))


class CardSessionCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_store = photo_crop_endpoints.STORE
        photo_crop_endpoints.STORE = photo_crop_endpoints.PhotoSessionStore(Path(self.temp.name))
        app = FastAPI()
        app.include_router(photo_crop_endpoints.router)
        self.client = TestClient(app)
        self.session_id = self.client.post("/api/photo-crop/sessions").json()["session_id"]
        self.photos = [self.upload(name) for name in ("ana.jpg", "luis.jpg", "sofía.jpg")]

    def tearDown(self):
        photo_crop_endpoints.STORE = self.original_store
        self.temp.cleanup()

    def upload(self, filename):
        response = self.client.post(
            f"/api/photo-crop/sessions/{self.session_id}/photos",
            params={"filename": filename},
            content=image_bytes(),
            headers={"Content-Type": "image/jpeg"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def items(self):
        return [
            {"photo_id": photo["id"], "crop": [0, 0, 640, 853], "sequence": index + 1,
             "metadata": {"Nombre": f"Persona {index}", "Apellido": "Pérez", "Legajo": f"L{index}"}}
            for index, photo in enumerate(self.photos)
        ]


class CardEndpointTests(CardSessionCase):
    def export(self, output, card_design=None, items=None):
        return self.client.post(
            f"/api/photo-crop/sessions/{self.session_id}/cards/export",
            json={"design": card_design or design(), "items": items or self.items(), "output": output},
        )

    def test_single_card_as_png_uses_filename_pattern(self):
        response = self.export({"format": "PNG", "dpi": 300, "filename_pattern": "{Apellido}_{Nombre}"}, items=self.items()[:1])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertIn("filename*=UTF-8''P%C3%A9rez_Persona%200.png", response.headers["content-disposition"])
        with Image.open(io.BytesIO(response.content)) as card:
            self.assertEqual(card.size, (1011, 638))
            self.assertAlmostEqual(card.info["dpi"][0], 300, places=1)

    def test_batch_both_sides_as_jpg_zip(self):
        response = self.export({"format": "JPG", "sides": "both"}, card_design=design(double_sided=True))
        self.assertEqual(response.status_code, 200, response.text)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = sorted(archive.namelist())
        self.assertEqual(len(names), 6)
        self.assertIn("ana_frente.jpg", names)
        self.assertIn("sofía_dorso.jpg", names)

    def test_back_requires_double_sided_design(self):
        response = self.export({"format": "PDF", "sides": "both"})
        self.assertEqual(response.status_code, 400)

    def test_pdf_one_card_per_page_has_real_size(self):
        response = self.export({"format": "PDF", "sides": "both", "pdf_layout": "card"}, card_design=design(double_sided=True))
        self.assertEqual(response.status_code, 200, response.text)
        document = fitz.open(stream=response.content, filetype="pdf")
        self.assertEqual(document.page_count, 6)
        self.assertAlmostEqual(document[0].rect.width, 85.6 / 25.4 * 72, places=1)
        self.assertAlmostEqual(document[0].rect.height, 53.98 / 25.4 * 72, places=1)

    def test_pdf_sheet_layout_groups_cards(self):
        response = self.export({"format": "PDF", "sides": "both", "pdf_layout": "sheet", "sheet": "A4"}, card_design=design(double_sided=True))
        self.assertEqual(response.status_code, 200, response.text)
        document = fitz.open(stream=response.content, filetype="pdf")
        self.assertEqual(document.page_count, 2)
        self.assertEqual(len(document[0].get_images()), 3)

    def test_preview_returns_png_at_requested_dpi(self):
        response = self.client.post(
            f"/api/photo-crop/sessions/{self.session_id}/cards/preview",
            json={"design": design(double_sided=True), "item": self.items()[0], "side": "back", "dpi": 100},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with Image.open(io.BytesIO(response.content)) as preview:
            self.assertEqual(preview.size, (337, 213))

    def test_assets_are_used_and_saved_in_project(self):
        uploaded = self.client.post(
            f"/api/photo-crop/sessions/{self.session_id}/assets",
            params={"filename": "logo.png"},
            content=image_bytes(size=(200, 100), color=(250, 10, 10), format_name="PNG"),
            headers={"Content-Type": "image/png"},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        asset_id = uploaded.json()["asset_id"]
        self.assertEqual(self.client.get(uploaded.json()["url"]).status_code, 200)
        card_design = design()
        card_design["front"]["elements"].append(
            {"id": "logo", "type": "image", "asset": asset_id, "x": 0, "y": 0, "w": 1, "h": 1, "image_fit": "stretch"}
        )
        response = self.export({"format": "PNG", "dpi": 100}, card_design=card_design, items=self.items()[:1])
        with Image.open(io.BytesIO(response.content)) as card:
            self.assertEqual(card.getpixel((100, 100))[:3], (250, 10, 10))

        saved = self.client.post(f"/api/photo-crop/sessions/{self.session_id}/project", json={"state": {"settings": {}}})
        self.assertEqual(saved.status_code, 200, saved.text)
        reopened = self.client.post(
            "/api/photo-crop/projects",
            params={"filename": "proyecto.recortador.zip"},
            content=saved.content,
            headers={"Content-Type": "application/zip"},
        )
        self.assertEqual(reopened.status_code, 201, reopened.text)
        self.assertEqual([asset["asset_id"] for asset in reopened.json()["assets"]], [asset_id])

    def test_code_previews(self):
        qr = self.client.get("/api/photo-crop/qr.svg", params={"value": "Hola", "color": "#123456"})
        self.assertEqual(qr.status_code, 200)
        self.assertTrue(qr.text.startswith("<svg"))
        barcode = self.client.get("/api/photo-crop/barcode.svg", params={"value": "590123412345", "symbology": "ean13"})
        self.assertEqual(barcode.status_code, 200, barcode.text)
        invalid = self.client.get("/api/photo-crop/barcode.svg", params={"value": "ABC", "symbology": "ean13"})
        self.assertEqual(invalid.status_code, 422)
        bad_color = self.client.get("/api/photo-crop/qr.svg", params={"value": "x", "color": "red\"/><script>"})
        self.assertEqual(bad_color.status_code, 422)

    def test_rejects_unknown_element_type_and_bad_color(self):
        card_design = design()
        card_design["front"]["elements"].append({"id": "x", "type": "script", "x": 0, "y": 0, "w": 1, "h": 1})
        self.assertEqual(self.export({"format": "PDF"}, card_design=card_design).status_code, 422)
        card_design = design()
        card_design["front"]["elements"][0]["fill"] = "red"
        self.assertEqual(self.export({"format": "PDF"}, card_design=card_design).status_code, 422)


class FakePrintJob:
    instances = []

    def __init__(self, printer, *, landscape, duplex, title, output_file=None):
        self.printer, self.landscape, self.duplex, self.title = printer, landscape, duplex, title
        self.cards = []
        self.pages = 0
        self.dpi = 300
        FakePrintJob.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def add_card(self, faces, *, rotate_back=False, encode=None):
        self.cards.append((faces, rotate_back))
        self.encodings = getattr(self, "encodings", []) + [encode]
        self.pages += len(faces)


class CardCheckAndPrintTests(CardSessionCase):
    def test_check_reports_missing_data_invalid_codes_and_cut_text(self):
        card_design = design()
        card_design["front"]["elements"] += [
            {"id": "ean", "type": "barcode", "x": 0.1, "y": 0.1, "w": 0.4, "h": 0.2, "value": "{Legajo}", "symbology": "ean13"},
            {"id": "largo", "type": "text", "x": 0.1, "y": 0.1, "w": 0.1, "h": 0.05, "fit": "none",
             "text": "Un texto demasiado largo para la caja"},
            {"id": "cargo", "type": "text", "x": 0.1, "y": 0.5, "w": 0.4, "h": 0.1, "text": "{Cargo}"},
        ]
        items = self.items()
        items[0]["issues"] = ["Posible desenfoque"]
        response = self.client.post(
            f"/api/photo-crop/sessions/{self.session_id}/cards/check",
            json={"design": card_design, "items": items, "sides": "front"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(report["checked"], 3)
        self.assertEqual(report["with_issues"], 3)
        messages = " | ".join(issue["message"] for issue in report["results"][0]["issues"])
        self.assertIn("código inválido", messages)
        self.assertIn("no entra completo", messages)
        self.assertIn("sin dato en {Cargo}", messages)
        self.assertIn("posible desenfoque", messages)
        self.assertGreaterEqual(report["errors"], 6)

    def test_check_without_issues(self):
        response = self.client.post(
            f"/api/photo-crop/sessions/{self.session_id}/cards/check",
            json={"design": design(), "items": self.items(), "sides": "front"},
        )
        self.assertEqual(response.json()["with_issues"], 0)

    def test_print_sends_one_page_per_face_and_logs(self):
        FakePrintJob.instances.clear()
        logged = []
        with patch.object(photo_crop_endpoints.card_printing, "CardPrintJob", FakePrintJob), \
                patch.object(photo_crop_endpoints.card_printing, "append_print_log", logged.extend):
            response = self.client.post(
                f"/api/photo-crop/sessions/{self.session_id}/cards/print",
                json={"design": design(double_sided=True), "items": self.items(), "printer": "Magicard Rio Pro",
                      "sides": "both", "copies": 2, "rotate_back": True},
            )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual((result["cards"], result["pages"]), (6, 12))
        job = FakePrintJob.instances[0]
        self.assertTrue(job.landscape and job.duplex)
        self.assertEqual(job.cards[0][0][0].size, (1011, 638))
        self.assertTrue(job.cards[0][1])
        self.assertEqual(len(logged), 3)
        self.assertEqual(logged[0][1], "Magicard Rio Pro")

    def test_print_reports_driver_errors(self):
        class Broken(FakePrintJob):
            def __enter__(self):
                raise photo_crop_endpoints.card_printing.CardPrintError("No se encontró la impresora “X”")

        with patch.object(photo_crop_endpoints.card_printing, "CardPrintJob", Broken):
            response = self.client.post(
                f"/api/photo-crop/sessions/{self.session_id}/cards/print",
                json={"design": design(), "items": self.items()[:1], "printer": "X"},
            )
        self.assertEqual(response.status_code, 502)
        self.assertIn("No se encontró", response.json()["detail"])

    def test_printer_list(self):
        printers = [{"name": "Zebra ZC300", "driver": "Zebra ZC300", "card": True, "default": False, "status": "Lista", "ready": True}]
        with patch.object(photo_crop_endpoints.card_printing, "list_printers", return_value=printers):
            response = self.client.get("/api/photo-crop/card-printers")
        self.assertEqual(response.json()["printers"][0]["name"], "Zebra ZC300")


class CardPrintingUnitTests(unittest.TestCase):
    def test_recognizes_card_printer_brands(self):
        from card_printing import is_card_printer
        for name in ("Zebra ZC300", "ZXP Series 7", "Magicard Rio Pro (V2)", "Magicard 600NEO", "XPS Card Printer",
                     "Entrust Sigma DS2", "Swiftpro K30 Card Printer", "Evolis Primacy 2"):
            self.assertTrue(is_card_printer(name, ""), name)
        for name in ("Godex GE300", "EPSON L1250 Series", "Microsoft Print to PDF", "POS-80-Series"):
            self.assertFalse(is_card_printer(name, ""), name)

    def test_page_is_rotated_to_driver_orientation_and_covers_page(self):
        from card_printing import CardPrintJob, PageGeometry

        drawn = []

        class FakeDC:
            def StartPage(self):
                pass

            def EndPage(self):
                pass

            def GetHandleOutput(self):
                return 0

        job = CardPrintJob("Swiftpro", landscape=True, duplex=False, title="t")
        job._dc = FakeDC()
        job.geometry = PageGeometry(width=664, height=1036, offset_x=0, offset_y=0, dpi=300)
        with patch("card_printing.ImageWin.Dib") as dib:
            dib.return_value.draw = lambda _hdc, rect: drawn.append(rect)
            job.add_card([Image.new("RGB", (1011, 638), "white")])
            fitted = dib.call_args[0][0]
        self.assertEqual(fitted.size, (664, 1036))
        self.assertEqual(drawn[0], (0, 0, 664, 1036))
        self.assertEqual(job.pages, 1)


if __name__ == "__main__":
    unittest.main()
