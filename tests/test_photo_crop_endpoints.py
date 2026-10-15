import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import face_detection
import photo_crop_endpoints
from photo_crop_service import ExportTransform, default_crop, process_background, render_export


def image_bytes(size=(640, 900), color=(105, 145, 185), format_name="JPEG"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format_name)
    return output.getvalue()


def pdf_bytes():
    output = io.BytesIO()
    first = Image.new("RGB", (180, 240), (230, 235, 240))
    second = Image.new("RGB", (180, 240), (205, 220, 235))
    first.save(output, "PDF", save_all=True, append_images=[second], resolution=100)
    return output.getvalue()


class PhotoCropApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_store = photo_crop_endpoints.STORE
        photo_crop_endpoints.STORE = photo_crop_endpoints.PhotoSessionStore(Path(self.temp.name))
        app = FastAPI()
        app.include_router(photo_crop_endpoints.router)
        self.client = TestClient(app)

    def tearDown(self):
        photo_crop_endpoints.STORE = self.original_store
        self.temp.cleanup()

    def create_session(self):
        response = self.client.post("/api/photo-crop/sessions")
        self.assertEqual(response.status_code, 201)
        return response.json()["session_id"]

    def upload(self, session_id, filename="persona.jpg"):
        response = self.client.post(
            f"/api/photo-crop/sessions/{session_id}/photos",
            params={"filename": filename},
            content=image_bytes(),
            headers={"Content-Type": "image/jpeg"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_upload_detect_and_export_zip(self):
        session_id = self.create_session()
        photo = self.upload(session_id)
        self.assertEqual((photo["width"], photo["height"]), (640, 900))
        self.assertTrue(photo["preview_url"].endswith("/preview"))

        face = face_detection.FaceResult(
            box=(210, 185, 210, 250),
            eye_line=265.0,
            eye_points=((265.0, 265.0), (365.0, 265.0)),
            roll=0.0,
            score=0.96,
            engine="yunet",
        )
        with patch.object(photo_crop_endpoints.face_detection, "detect_primary_face", return_value=face), patch.object(
            photo_crop_endpoints.face_detection, "engine_note", return_value=""
        ):
            detected = self.client.post(
                f"/api/photo-crop/sessions/{session_id}/detect",
                json={"ratio": 0.75},
            )
        self.assertEqual(detected.status_code, 200, detected.text)
        result = detected.json()["results"][0]
        self.assertTrue(result["face_found"])
        self.assertEqual(result["engine"], "yunet")
        crop = result["crop"]
        self.assertAlmostEqual((crop[2] - crop[0]) / (crop[3] - crop[1]), 0.75, places=4)

        exported = self.client.post(
            f"/api/photo-crop/sessions/{session_id}/export",
            json={
                "format": "JPG",
                "width": 300,
                "height": 400,
                "suffix": "_credencial",
                "items": [{"photo_id": photo["id"], "crop": crop, "brightness": 1.05, "contrast": 1.1}],
            },
        )
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertEqual(exported.headers["content-type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            self.assertEqual(set(archive.namelist()), {"persona_credencial.jpg", "registro_lote.csv"})
            with Image.open(io.BytesIO(archive.read("persona_credencial.jpg"))) as final:
                self.assertEqual(final.size, (300, 400))

    def test_reframing_reuses_detection_and_honors_face_fill(self):
        session_id = self.create_session()
        photo = self.upload(session_id)
        face = face_detection.FaceResult(
            box=(260, 300, 120, 150), eye_line=360.0, eye_points=((290.0, 360.0), (350.0, 360.0)),
            roll=0.0, score=0.95, engine="yunet",
        )
        with patch.object(photo_crop_endpoints.face_detection, "detect_primary_face", return_value=face) as detector, \
                patch.object(photo_crop_endpoints.face_detection, "engine_note", return_value=""):
            sizes = []
            for fill in (0.4, 0.7):
                response = self.client.post(
                    f"/api/photo-crop/sessions/{session_id}/detect",
                    json={"ratio": 1, "face_fill": fill, "eye_position": 45},
                )
                self.assertEqual(response.status_code, 200, response.text)
                crop = response.json()["results"][0]["crop"]
                self.assertAlmostEqual(crop[2] - crop[0], crop[3] - crop[1], places=4)
                sizes.append(crop[3] - crop[1])
                self.assertAlmostEqual((360 - crop[1]) / (crop[3] - crop[1]), 0.45, places=2)
        self.assertEqual(detector.call_count, 1)
        self.assertAlmostEqual(sizes[0], 150 / 0.4, places=1)
        self.assertAlmostEqual(sizes[1], 150 / 0.7, places=1)
        self.assertTrue(photo["id"])

    def test_rejects_cross_origin_mutations(self):
        response = self.client.post(
            "/api/photo-crop/sessions",
            headers={"Origin": "https://sitio-no-autorizado.example"},
        )
        self.assertEqual(response.status_code, 403)

    def test_rejects_invalid_image_and_extension(self):
        session_id = self.create_session()
        unsupported = self.client.post(
            f"/api/photo-crop/sessions/{session_id}/photos",
            params={"filename": "documento.exe"},
            content=b"not-an-image",
        )
        self.assertEqual(unsupported.status_code, 415)
        invalid = self.client.post(
            f"/api/photo-crop/sessions/{session_id}/photos",
            params={"filename": "falsa.jpg"},
            content=b"not-an-image",
        )
        self.assertEqual(invalid.status_code, 415)

    def test_delete_session_removes_temporary_files(self):
        session_id = self.create_session()
        self.upload(session_id)
        folder = photo_crop_endpoints.STORE.get(session_id).folder
        self.assertTrue(folder.exists())
        response = self.client.delete(f"/api/photo-crop/sessions/{session_id}")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(folder.exists())

    def test_imports_pdf_and_tabular_data(self):
        session_id = self.create_session()
        imported = self.client.post(
            f"/api/photo-crop/sessions/{session_id}/pdf",
            params={"filename": "personas.pdf"},
            content=pdf_bytes(),
            headers={"Content-Type": "application/pdf"},
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertEqual(imported.json()["pages"], 2)
        self.assertEqual(len(imported.json()["photos"]), 2)

        csv_content = "Nombre;Apellido;Cargo\nAna;Pérez;Ventas\nLuis;Gómez;Depósito\n".encode("utf-8")
        data = self.client.post(
            f"/api/photo-crop/sessions/{session_id}/data",
            params={"filename": "personas.csv"},
            content=csv_content,
        )
        self.assertEqual(data.status_code, 200, data.text)
        self.assertEqual(data.json()["headers"], ["Nombre", "Apellido", "Cargo"])
        self.assertEqual(data.json()["rows"][0]["Nombre"], "Ana")

    def test_card_export_review_pdf_and_project_round_trip(self):
        session_id = self.create_session()
        photo = self.upload(session_id, "ana_perez.jpg")
        fonts_response = self.client.get("/api/photo-crop/fonts")
        self.assertEqual(fonts_response.status_code, 200, fonts_response.text)
        fonts = fonts_response.json()["fonts"]
        self.assertTrue(fonts)
        selected_font = next((font["id"] for font in fonts if font["label"] == "Arial"), "sans")
        background = self.client.post(
            f"/api/photo-crop/sessions/{session_id}/card-background",
            params={"filename": "fondo.png"},
            content=image_bytes(size=(900, 600), color=(238, 242, 247), format_name="PNG"),
            headers={"Content-Type": "image/png"},
        )
        self.assertEqual(background.status_code, 201, background.text)
        payload = {
            "format": "PNG",
            "width": 300,
            "height": 400,
            "background_mode": "original",
            "card_design": {
                "width_mm": 53.98,
                "height_mm": 85.6,
                "front": {
                    "background_color": "#f9fafc",
                    "background_image": "card_background",
                    "elements": [
                        {"id": "titulo", "type": "text", "x": 0.1, "y": 0.04, "w": 0.8, "h": 0.08,
                         "text": "EMPRESA", "font": selected_font, "bold": True, "align": "center"},
                        {"id": "foto", "type": "photo", "x": 0.2, "y": 0.15, "w": 0.6, "h": 0.45, "shape": "circle"},
                        {"id": "nombre", "type": "text", "x": 0.05, "y": 0.64, "w": 0.9, "h": 0.08,
                         "text": "{Nombre}", "align": "right", "uppercase": True},
                        {"id": "qr", "type": "qr", "x": 0.6, "y": 0.78, "w": 0.3, "h": 0.18, "value": "{Legajo}"},
                    ],
                },
            },
            "items": [{
                "photo_id": photo["id"],
                "crop": [0, 0, 640, 900],
                "approved": True,
                "metadata": {"Nombre": "Ana Pérez", "Cargo": "Ventas", "Legajo": "A-100"},
            }],
        }
        exported = self.client.post(f"/api/photo-crop/sessions/{session_id}/export", json=payload)
        self.assertEqual(exported.status_code, 200, exported.text)
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            with Image.open(io.BytesIO(archive.read("ana_perez.png"))) as card:
                self.assertEqual(card.size, (638, 1011))

        review = self.client.post(f"/api/photo-crop/sessions/{session_id}/review-pdf", json=payload)
        self.assertEqual(review.status_code, 200, review.text)
        self.assertTrue(review.content.startswith(b"%PDF"))

        saved_state = {
            "photos": {photo["id"]: {"crop": [10, 20, 620, 880], "approved": True}},
            "settings": {"aspect": "0.75", "cardTitle": "EMPRESA"},
            "data": {"headers": ["Nombre"], "rows": [{"Nombre": "Ana Pérez"}]},
        }
        saved = self.client.post(
            f"/api/photo-crop/sessions/{session_id}/project",
            json={"state": saved_state},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        reopened = self.client.post(
            "/api/photo-crop/projects",
            params={"filename": "proyecto.recortador.zip"},
            content=saved.content,
            headers={"Content-Type": "application/zip"},
        )
        self.assertEqual(reopened.status_code, 201, reopened.text)
        restored = reopened.json()
        self.assertEqual(len(restored["photos"]), 1)
        self.assertTrue(restored["photos"][0]["state"]["approved"])
        self.assertEqual(restored["state"]["settings"]["cardTitle"], "EMPRESA")
        self.assertIsNotNone(restored["card_background_url"])


class PhotoCropServiceTests(unittest.TestCase):
    def test_rotation_and_crop_use_rotated_coordinates(self):
        source = Image.new("RGB", (200, 100), "white")
        source.paste((255, 0, 0), (0, 0, 50, 100))
        result = render_export(
            source,
            ExportTransform(crop=(0, 0, 50, 100), rotation=90),
            output_size=None,
        )
        self.assertEqual(result.size, (50, 100))

    def test_default_crop_preserves_requested_ratio(self):
        crop = default_crop((1200, 800), 0.75)
        self.assertAlmostEqual((crop[2] - crop[0]) / (crop[3] - crop[1]), 0.75)

    def test_background_processing_preserves_dimensions(self):
        source = Image.new("RGB", (240, 320), (80, 90, 100))
        source.paste((185, 80, 65), (70, 30, 170, 300))
        result = process_background(source, "light", 80)
        self.assertEqual(result.size, source.size)
        self.assertNotEqual(result.getpixel((5, 5)), source.getpixel((5, 5)))


if __name__ == "__main__":
    unittest.main()
