import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "api"))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from client_assets_endpoints import router


class TestClientAssetsEndpoints(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_search_forwards_match_mode(self):
        payload = {"client_name": "Arcos", "match_count": 0, "items": [], "warnings": [], "match_mode": "broad"}

        with patch("client_assets_endpoints.client_assets_service.search_client_assets", return_value=payload) as search_mock:
            response = self.client.get("/api/client-assets/search", params={"client_name": "Arcos", "match_mode": "broad"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        search_mock.assert_called_once_with("Arcos", "broad")

    def test_open_in_corel_returns_payload(self):
        payload = {
            "ok": True,
            "mode": "open_only",
            "profile_id": None,
            "item_id": "abc123",
            "file_name": "IAC_credito_2025.cdr",
            "relative_path": "I\\Instituto Antonio Carbajal\\IAC_credito_2025.cdr",
            "message": "Archivo abierto en CorelDRAW.",
            "warnings": [],
            "applied_settings": {},
            "macro_result": {},
        }

        with patch("client_assets_endpoints.client_assets_service.open_in_corel", return_value=payload) as open_mock:
            response = self.client.post("/api/client-assets/open-in-corel", json={"item_id": "abc123", "mode": "open_only"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        open_mock.assert_called_once_with("abc123", "open_only", None)

    def test_open_and_prepare_in_corel_returns_payload(self):
        payload = {
            "ok": True,
            "mode": "open_and_prepare",
            "profile_id": "tarjetas_plasticas",
            "item_id": "abc123",
            "file_name": "IAC_credito_2025.cdr",
            "relative_path": "I\\Instituto Antonio Carbajal\\IAC_credito_2025.cdr",
            "message": "Archivo abierto y preparado en CorelDRAW.",
            "warnings": [],
            "applied_settings": {
                "printer_name": {"value": "Printer PVC", "target": "document.PrintSettings.PrinterName"},
            },
            "macro_result": {"used": False, "status": "disabled"},
        }

        with patch("client_assets_endpoints.client_assets_service.open_in_corel", return_value=payload) as open_mock:
            response = self.client.post(
                "/api/client-assets/open-in-corel",
                json={"item_id": "abc123", "mode": "open_and_prepare", "profile_id": "tarjetas_plasticas"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        open_mock.assert_called_once_with("abc123", "open_and_prepare", "tarjetas_plasticas")

    def test_open_in_corel_returns_404_when_file_is_missing(self):
        with patch(
            "client_assets_endpoints.client_assets_service.open_in_corel",
            side_effect=FileNotFoundError("No existe el archivo solicitado."),
        ):
            response = self.client.post("/api/client-assets/open-in-corel", json={"item_id": "abc123", "mode": "open_only"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "No existe el archivo solicitado.")

    def test_open_in_corel_returns_400_for_validation_or_corel_errors(self):
        with patch(
            "client_assets_endpoints.client_assets_service.open_in_corel",
            side_effect=ValueError("No se pudo abrir el archivo en CorelDRAW."),
        ):
            response = self.client.post("/api/client-assets/open-in-corel", json={"item_id": "abc123", "mode": "open_only"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "No se pudo abrir el archivo en CorelDRAW.")

    def test_prewarm_previews_returns_payload(self):
        payload = {
            "ok": True,
            "requested_count": 2,
            "processed_count": 2,
            "warmed_count": 1,
            "cached_count": 1,
            "failed_count": 0,
            "items": [
                {"item_id": "abc123", "status": "cached", "preview_path": "C:\\cache\\abc123.png"},
                {"item_id": "def456", "status": "warmed", "preview_path": "C:\\cache\\def456.png"},
            ],
        }

        with patch("client_assets_endpoints.client_assets_service.prewarm_previews", return_value=payload) as prewarm_mock:
            response = self.client.post(
                "/api/client-assets/prewarm-previews",
                json={"item_ids": ["abc123", "def456"], "limit": 8, "force_refresh": False},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        prewarm_mock.assert_called_once_with(["abc123", "def456"], 8, False)

    def test_prewarm_previews_returns_400_for_invalid_payload(self):
        with patch(
            "client_assets_endpoints.client_assets_service.prewarm_previews",
            side_effect=ValueError("item_ids vacio"),
        ):
            response = self.client.post(
                "/api/client-assets/prewarm-previews",
                json={"item_ids": [], "limit": 8, "force_refresh": False},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "item_ids vacio")


if __name__ == "__main__":
    unittest.main()
