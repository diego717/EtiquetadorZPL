import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "api"))

from mercadolibre_integration import MercadoLibreIntegration  # noqa: E402
import mercadolibre_endpoints as endpoints  # noqa: E402


class TestMercadoLibreManualTokens(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.integration = MercadoLibreIntegration()
        self.integration.config_path = Path(self.temp_dir.name) / "mercadolibre_config.json"
        self.integration.config = self.integration._default_config()

    def test_manual_tokens_are_saved_masked_and_mark_config_authenticated(self):
        with patch("mercadolibre_integration.time.time", return_value=1_000_000):
            result = self.integration.save_manual_tokens(
                access_token=" APP_USR-test ",
                refresh_token=" TG-test ",
                expires_in=21600,
                user_id=123456,
            )

        self.assertTrue(result["authenticated"])
        self.assertTrue(result["has_access_token"])
        self.assertTrue(result["has_refresh_token"])
        self.assertEqual(result["access_token"], "***")
        self.assertEqual(result["refresh_token"], "***")
        self.assertEqual(result["expires_at"], 1_021_540)
        self.assertEqual(result["user_id"], 123456)

        saved = json.loads(self.integration.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["access_token"], "APP_USR-test")
        self.assertEqual(saved["refresh_token"], "TG-test")

    def test_blank_refresh_token_preserves_existing_one(self):
        self.integration.config["refresh_token"] = "TG-existing"

        self.integration.save_manual_tokens(
            access_token="APP_USR-new",
            refresh_token="",
        )

        self.assertEqual(self.integration.config["refresh_token"], "TG-existing")
        self.assertEqual(self.integration.config["expires_at"], 0)

    def test_access_token_is_required_for_manual_import(self):
        with self.assertRaisesRegex(ValueError, "access_token"):
            self.integration.save_manual_tokens(access_token="   ")


class _FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _FakeHttpClient:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0

    def request(self, **kwargs):
        self.calls += 1
        status, headers = self.statuses.pop(0)
        return _FakeResponse(status, headers)


class TestMercadoLibreRateLimit(unittest.TestCase):
    def _integration(self):
        integration = MercadoLibreIntegration()
        integration.ensure_token = lambda: "token"
        integration.config = {"access_token": "token"}
        return integration

    def test_request_retries_429_respecting_retry_after(self):
        client = _FakeHttpClient([(429, {"Retry-After": "3"}), (200, {})])
        with patch("mercadolibre_integration.get_sync_http_client", return_value=client), patch(
            "mercadolibre_integration.time.sleep"
        ) as sleep:
            response = self._integration().request("GET", "/orders/search")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.calls, 2)
        sleep.assert_called_once_with(3.0)

    def test_request_gives_up_after_retries_with_capped_wait(self):
        client = _FakeHttpClient([(429, {"Retry-After": "120"})] * 4)
        with patch("mercadolibre_integration.get_sync_http_client", return_value=client), patch(
            "mercadolibre_integration.time.sleep"
        ) as sleep:
            response = self._integration().request("GET", "/orders/search")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(client.calls, 4)
        self.assertEqual(sleep.call_count, 3)
        self.assertTrue(all(call.args[0] <= 10.0 for call in sleep.call_args_list))


class TestMercadoLibreManualTokenEndpoint(unittest.TestCase):
    def test_config_endpoint_forwards_manual_token_fields(self):
        request = endpoints.MercadoLibreConfigRequest(
            enabled=True,
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="https://example.test/callback",
            access_token="APP_USR-test",
            refresh_token="TG-test",
            expires_in=21600,
            user_id=123456,
        )
        expected = {"authenticated": True, "access_token": "***"}
        verified = {
            "authenticated": True,
            "access_token": "***",
            "user_id": 38774586,
            "nickname": "ARAMID",
        }

        with patch.object(
            endpoints.mercadolibre_integration,
            "save_config",
            side_effect=[{}, verified],
        ) as save_config, patch.object(
            endpoints.mercadolibre_integration,
            "save_manual_tokens",
            return_value=expected,
        ) as save_tokens, patch.object(
            endpoints.mercadolibre_integration,
            "get_me",
            return_value={"id": 38774586, "nickname": "ARAMID"},
        ):
            result = asyncio.run(endpoints.save_config(request))

        self.assertEqual(result, verified)
        ordinary_payload = save_config.call_args_list[0].args[0]
        self.assertNotIn("access_token", ordinary_payload)
        self.assertNotIn("refresh_token", ordinary_payload)
        self.assertNotIn("expires_in", ordinary_payload)
        self.assertNotIn("user_id", ordinary_payload)
        save_tokens.assert_called_once_with(
            access_token="APP_USR-test",
            refresh_token="TG-test",
            expires_in=21600,
            user_id=123456,
        )
        self.assertEqual(
            save_config.call_args_list[1].args[0],
            {"user_id": 38774586, "nickname": "ARAMID", "last_error": ""},
        )

    def test_blank_sensitive_fields_preserve_saved_credentials(self):
        request = endpoints.MercadoLibreConfigRequest(
            client_id="client-id",
            client_secret="",
            access_token="",
            refresh_token="",
        )
        expected = {"authenticated": True, "has_access_token": True}

        with patch.object(
            endpoints.mercadolibre_integration,
            "save_config",
            return_value={},
        ) as save_config, patch.object(
            endpoints.mercadolibre_integration,
            "save_manual_tokens",
        ) as save_tokens, patch.object(
            endpoints.mercadolibre_integration,
            "get_public_config",
            return_value=expected,
        ):
            result = asyncio.run(endpoints.save_config(request))

        self.assertEqual(result, expected)
        self.assertNotIn("client_secret", save_config.call_args.args[0])
        save_tokens.assert_not_called()


class _FakePaymentOdoo:
    def __init__(self, operator_exists=True):
        self.operator_exists = operator_exists
        self.authenticated_with = None

    def is_configured(self):
        return True

    def get_payment_journals(self):
        return [{"id": 12, "name": "Mercado Pago $", "type": "bank"}]

    def get_rounding_accounts(self):
        return [{"id": 31, "code": "5.1.9", "name": "Redondeos"}]

    def get_operator_odoo_users_public(self):
        return [{"app_username": "vale", "odoo_username": "vale@example.com", "has_password": True}]

    def resolve_operator_auth_exact(self, operator):
        if self.operator_exists and operator == "vale":
            return {"username": "vale@example.com", "password": "secret"}
        return None

    def _authenticate(self, auth_override=None):
        self.authenticated_with = dict(auth_override or {})
        return 25


class _FakePaymentMercadoLibre:
    def __init__(self):
        self.saved = []

    def is_authenticated(self):
        return True

    def save_config(self, updates):
        self.saved.append(dict(updates))


class TestMercadoLibrePaymentEndpoints(unittest.TestCase):
    def setUp(self):
        # Registrar un pago escribe en el historial compartido de pagos: sin esto los tests
        # agregaban pagos falsos al historial real del usuario.
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self.state_patcher = patch.object(endpoints.recon, "_resolve_state_path", lambda name: tmp_path / name)
        self.state_patcher.start()

    def tearDown(self):
        self.state_patcher.stop()
        self.tmp.cleanup()

    def test_payment_options_do_not_expose_operator_passwords(self):
        fake_odoo = _FakePaymentOdoo()
        with patch.object(endpoints, "odoo_integration", fake_odoo):
            result = asyncio.run(endpoints.get_payment_options())

        self.assertEqual(result["journals"][0]["name"], "Mercado Pago $")
        self.assertEqual(result["rounding_accounts"][0]["name"], "Redondeos")
        self.assertEqual(result["operators"][0]["odoo_username"], "vale@example.com")
        self.assertNotIn("password", result["operators"][0])

    def test_register_payment_rejects_unknown_operator_before_writing(self):
        request = endpoints.RegisterMercadoLibrePaymentRequest(
            order_id="2000015420705457",
            journal_id=12,
            operator_app_username="desconocido",
        )
        with patch.object(endpoints, "odoo_integration", _FakePaymentOdoo(operator_exists=False)), patch.object(
            endpoints, "mercadolibre_integration", _FakePaymentMercadoLibre()
        ):
            with self.assertRaises(endpoints.HTTPException) as caught:
                asyncio.run(endpoints.register_mercadolibre_payment(request))

        self.assertIn("Selecciona un operador", caught.exception.detail)

    def test_register_payment_forwards_verified_operator_to_service(self):
        fake_odoo = _FakePaymentOdoo()
        fake_meli = _FakePaymentMercadoLibre()
        request = endpoints.RegisterMercadoLibrePaymentRequest(
            order_id="2000015420705457",
            journal_id=12,
            operator_app_username="VALE",
            rounding_account_id=31,
        )
        expected = {"ok": True, "attachment_ok": True}
        with patch.object(endpoints, "odoo_integration", fake_odoo), patch.object(
            endpoints, "mercadolibre_integration", fake_meli
        ), patch.object(
            endpoints.payment_service, "register_order_payment", return_value=expected
        ) as register:
            result = asyncio.run(endpoints.register_mercadolibre_payment(request))

        auth = {"username": "vale@example.com", "password": "secret"}
        register.assert_called_once_with(
            fake_meli,
            fake_odoo,
            order_id="2000015420705457",
            journal_id=12,
            auth_override=auth,
            rounding_account_id=31,
        )
        self.assertEqual(fake_odoo.authenticated_with, auth)
        self.assertEqual(result["actor_app_username"], "vale")
        self.assertEqual(result["actor_odoo_username"], "vale@example.com")

    def _register_with_history(self, record_side_effect=None):
        request = endpoints.RegisterMercadoLibrePaymentRequest(
            order_id="2000018868191948",
            journal_id=12,
            operator_app_username="vale",
        )
        service_result = {
            "ok": True,
            "attachment_ok": True,
            "order": {
                "reference": "2000015420705457",
                "pack_id": "2000015420705457",
                "order_ids": ["2000018868191948"],
                "payment_reference": "182038050669",
                "buyer": "MARIA.BMB",
                "payment_date": "2026-10-08",
                "currency": "UYU",
                "shipping_amount": 260.0,
            },
            "invoice": {"id": 100, "name": "e-Ticket A-31028"},
            "result": {"payment_id": 951},
            "payment_amount": 1154.0,
            "rounding_difference": 0.01,
        }
        with patch.object(endpoints, "odoo_integration", _FakePaymentOdoo()), patch.object(
            endpoints, "mercadolibre_integration", _FakePaymentMercadoLibre()
        ), patch.object(
            endpoints.payment_service, "register_order_payment", return_value=service_result
        ), patch.object(
            endpoints.recon, "record_external_payments", side_effect=record_side_effect
        ) as record:
            result = asyncio.run(endpoints.register_mercadolibre_payment(request))
        return result, record

    def test_register_payment_is_saved_in_shared_payment_history(self):
        _result, record = self._register_with_history()

        entry = record.call_args.args[0][0]
        self.assertEqual(entry["source"], "mercadolibre")
        self.assertTrue(entry["ok"])
        self.assertEqual(entry["invoice_name"], "e-Ticket A-31028")
        self.assertEqual(entry["payment_id"], 951)
        self.assertEqual(entry["actor_odoo_username"], "vale@example.com")
        self.assertEqual(entry["mercadolibre"]["reference"], "2000015420705457")
        self.assertEqual(entry["mercadolibre"]["amount"], 1154.0)

    def test_rate_limit_error_is_explained_to_the_operator(self):
        class _RateLimited(Exception):
            response = _FakeResponse(429)

        with patch.object(endpoints, "odoo_integration", _FakePaymentOdoo()), patch.object(
            endpoints, "mercadolibre_integration", _FakePaymentMercadoLibre()
        ), patch.object(
            endpoints.payment_service, "build_payment_proposal", side_effect=_RateLimited("429")
        ):
            with self.assertRaises(endpoints.HTTPException) as caught:
                asyncio.run(endpoints.build_payment_proposal(endpoints.SyncSalesRequest(limit=40)))

        self.assertIn("Espera un minuto", caught.exception.detail)

    def test_history_failure_does_not_report_registered_payment_as_failed(self):
        result, _record = self._register_with_history(OSError("disco lleno"))

        self.assertTrue(result["ok"])
        self.assertIn("historial", result["warning"])


if __name__ == "__main__":
    unittest.main()
