import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "api"))

import remote_access  # noqa: E402

TUNNEL = {"cf-connecting-ip": "190.64.1.2", "cf-ray": "8abc-GRU"}


class NeedsLoginTests(unittest.TestCase):
    def test_local_requests_never_need_login(self):
        self.assertFalse(remote_access.needs_login("/api/mercadolibre/payments/register", "POST", {}))

    def test_tunnel_api_request_without_token_needs_login(self):
        self.assertTrue(remote_access.needs_login("/api/mercadolibre/payments/register", "POST", TUNNEL))

    def test_tunnel_static_pages_stay_public(self):
        self.assertFalse(remote_access.needs_login("/web/login.html", "GET", TUNNEL))
        self.assertFalse(remote_access.needs_login("/web/config.html", "GET", TUNNEL))

    def test_tunnel_public_api_paths(self):
        for path in ("/api/status", "/api/auth/login", "/api/mercadolibre/webhook", "/api/mercadolibre/oauth/callback"):
            self.assertFalse(remote_access.needs_login(path, "POST", TUNNEL), path)

    def test_prefix_lookalike_is_not_public(self):
        self.assertTrue(remote_access.needs_login("/api/auth/login-extra", "POST", TUNNEL))
        self.assertFalse(remote_access.needs_login("/apiX", "GET", TUNNEL))

    def test_preflight_is_allowed(self):
        self.assertFalse(remote_access.needs_login("/api/odoo/config", "OPTIONS", TUNNEL))

    def test_valid_token_passes_and_invalid_fails(self):
        headers = dict(TUNNEL, authorization="Bearer good")
        with patch.object(remote_access.cloud_auth_service, "verify_token", side_effect=lambda t: {"sub": "x"} if t == "good" else None):
            self.assertFalse(remote_access.needs_login("/api/odoo/config", "GET", headers))
            self.assertTrue(remote_access.needs_login("/api/odoo/config", "GET", dict(TUNNEL, authorization="Bearer bad")))
            self.assertTrue(remote_access.needs_login("/api/odoo/config", "GET", dict(TUNNEL, authorization="Basic good")))

    def test_response_marks_login_required(self):
        response = remote_access.login_required_response()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get(remote_access.LOGIN_REQUIRED_HEADER), "1")


if __name__ == "__main__":
    unittest.main()
