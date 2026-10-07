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


if __name__ == "__main__":
    unittest.main()
