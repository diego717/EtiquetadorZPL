import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from totalnet_integration import TotalNetIntegration


class TestTotalNetIntegration(unittest.TestCase):
    def setUp(self):
        self.integration = TotalNetIntegration()
        self.integration.config["api_base_url"] = "https://totalnet.test"
        self.integration._get_token = lambda: "token"

    @staticmethod
    def _response(status_code, json_data):
        request = httpx.Request("POST", "https://totalnet.test/cupones")
        return httpx.Response(status_code, json=json_data, request=request)

    def test_no_results_message_ends_pagination_without_error(self):
        response = self._response(
            404,
            {"message": "No se encontraron resultados para la consulta."},
        )

        with patch("totalnet_integration.httpx.post", return_value=response):
            result = self.integration._post(
                "/cupones",
                {"page_number": 4},
                allow_no_results=True,
            )

        self.assertTrue(result["_no_results"])
        self.assertEqual(result["detail"], "No se encontraron resultados para la consulta.")

    def test_unrelated_404_is_still_reported_as_an_error(self):
        response = self._response(404, {"message": "Ruta inexistente"})

        with patch("totalnet_integration.httpx.post", return_value=response):
            with self.assertRaisesRegex(ValueError, "TotalNet devolvio 404"):
                self.integration._post(
                    "/cupones",
                    {"page_number": 1},
                    allow_no_results=True,
                )

    def test_documented_transient_error_is_retried(self):
        unavailable = self._response(503, {"message": "Temporalmente no disponible"})
        success = self._response(200, {"cupones": [], "total_pages": 1})

        with (
            patch("totalnet_integration.httpx.post", side_effect=[unavailable, success]) as post,
            patch("totalnet_integration.time.sleep") as sleep,
        ):
            result = self.integration._post("/cupones", {"page_number": 1})

        self.assertEqual(result["cupones"], [])
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_internal_error_is_not_retried_and_preserves_activity_id(self):
        response = self._response(
            500,
            {
                "statusCode": 500,
                "message": "Internal server error",
                "activityId": "activity-test-123",
            },
        )

        with patch("totalnet_integration.httpx.post", return_value=response) as post:
            with self.assertRaisesRegex(ValueError, "activity-test-123"):
                self.integration._post("/cupones", {"page_number": 1})

        post.assert_called_once()

    def test_range_error_identifies_exact_date_and_page(self):
        failed_date = (date.today() - timedelta(days=3)).isoformat()
        with patch.object(
            self.integration,
            "get_cupones",
            side_effect=ValueError("TotalNet tuvo un error interno"),
        ):
            with self.assertRaisesRegex(
                ValueError,
                rf"{failed_date}, pagina 1: TotalNet tuvo un error interno",
            ):
                self.integration.get_all_cupones(failed_date, failed_date)

    def test_today_is_rejected_before_calling_totalnet(self):
        today = date.today().isoformat()
        with patch.object(self.integration, "get_cupones") as get_cupones:
            with self.assertRaisesRegex(ValueError, "fecha actual"):
                self.integration.get_all_cupones(today, today)

        get_cupones.assert_not_called()

    def test_get_info_requires_comercio_and_sucursal(self):
        self.integration.config["comercio"] = ""
        self.integration.config["sucursal"] = ""

        with self.assertRaisesRegex(ValueError, "comercio y sucursal"):
            self.integration.get_info()

    def test_get_info_posts_comercio_and_sucursal_and_returns_raw_response(self):
        self.integration.config["comercio"] = "2042823"
        self.integration.config["sucursal"] = "1"
        response = self._response(200, {"fechas_liquidacion_disponibles": ["2026-08-14"]})

        with patch("totalnet_integration.httpx.post", return_value=response) as post:
            result = self.integration.get_info()

        self.assertEqual(result, {"fechas_liquidacion_disponibles": ["2026-08-14"]})
        sent_payload = post.call_args.kwargs["json"]
        self.assertEqual(sent_payload, {"comercio": 2042823, "sucursal": 1})


if __name__ == "__main__":
    unittest.main()
