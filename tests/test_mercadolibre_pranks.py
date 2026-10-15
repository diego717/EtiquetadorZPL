import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))

import mercadolibre_endpoints as endpoints  # noqa: E402


class _FakeIntegration:
    def __init__(self):
        self.config = {"client_id": "x"}
        self.saved = []

    def save_config(self, updates):
        self.saved.append(dict(updates))
        self.config.update(updates)
        return dict(self.config)


class TestPranksSetting(unittest.TestCase):
    def test_disabled_by_default_and_toggle_persists_only_its_own_keys(self):
        fake = _FakeIntegration()
        with patch.object(endpoints, "mercadolibre_integration", fake):
            self.assertEqual(asyncio.run(endpoints.get_pranks()), {"enabled": False, "frequency": "always", "kind": "confirmations"})
            asyncio.run(endpoints.save_pranks(endpoints.PranksConfigRequest(enabled=True)))
            self.assertEqual(asyncio.run(endpoints.get_pranks()), {"enabled": True, "frequency": "always", "kind": "confirmations"})
            # Cambiar la frecuencia no toca el interruptor, y al reves.
            asyncio.run(endpoints.save_pranks(endpoints.PranksConfigRequest(frequency="daily")))
            self.assertEqual(asyncio.run(endpoints.get_pranks()), {"enabled": True, "frequency": "daily", "kind": "confirmations"})
            asyncio.run(endpoints.save_pranks(endpoints.PranksConfigRequest(enabled=False)))
            self.assertEqual(asyncio.run(endpoints.get_pranks()), {"enabled": False, "frequency": "daily", "kind": "confirmations"})
        self.assertEqual(fake.saved, [
            {"payment_prank_enabled": True},
            {"payment_prank_frequency": "daily"},
            {"payment_prank_enabled": False},
        ])
        # No toca credenciales ni el resto de la configuracion.
        self.assertEqual(fake.config["client_id"], "x")

    def test_kind_is_saved_on_its_own(self):
        fake = _FakeIntegration()
        with patch.object(endpoints, "mercadolibre_integration", fake):
            result = asyncio.run(endpoints.save_pranks(endpoints.PranksConfigRequest(kind="dodge")))
        self.assertEqual(result["kind"], "dodge")
        self.assertEqual(fake.saved, [{"payment_prank_kind": "dodge"}])

    def test_rejects_unknown_frequency(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            endpoints.PranksConfigRequest(frequency="hourly")
        with self.assertRaises(ValidationError):
            endpoints.PranksConfigRequest(kind="explosion")

if __name__ == "__main__":
    unittest.main()
