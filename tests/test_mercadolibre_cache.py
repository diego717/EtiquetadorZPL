import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mercadolibre_cache import PersistentCache  # noqa: E402
from mercadolibre_integration import MercadoLibreIntegration  # noqa: E402


class _JsonResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class TestPersistentCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "mercadolibre_cache.json"

    def _cache(self, **kwargs):
        return PersistentCache(lambda: self.path, **kwargs)

    def test_values_survive_a_new_instance(self):
        self._cache().set("shipment_costs:1", {"receiver": {"cost": 260}})

        self.assertEqual(self._cache().get("shipment_costs:1"), {"receiver": {"cost": 260}})

    def test_expired_values_are_ignored(self):
        cache = self._cache(ttl_seconds=60)
        with patch("mercadolibre_cache.time.time", return_value=1000.0):
            cache.set("pack:1", {"orders": [{"id": 1}]})
        with patch("mercadolibre_cache.time.time", return_value=1061.0):
            self.assertIsNone(cache.get("pack:1"))

    def test_keeps_only_newest_entries(self):
        cache = self._cache(max_entries=2)
        for index in range(3):
            with patch("mercadolibre_cache.time.time", return_value=1000.0 + index):
                cache.set(f"k{index}", index)

        reloaded = self._cache()
        with patch("mercadolibre_cache.time.time", return_value=1003.0):
            self.assertIsNone(reloaded.get("k0"))
            self.assertEqual(reloaded.get("k1"), 1)
            self.assertEqual(reloaded.get("k2"), 2)

    def test_corrupt_file_is_treated_as_empty(self):
        self.path.write_text("{no es json", encoding="utf-8")

        self.assertIsNone(self._cache().get("pack:1"))


class TestMercadoLibreCachedCalls(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.integration = MercadoLibreIntegration()
        path = Path(self.temp_dir.name) / "mercadolibre_cache.json"
        self.integration.cache = PersistentCache(lambda: path)
        self.calls = []

        def fake_request(method, resource, **kwargs):
            self.calls.append(resource)
            if resource.startswith("/packs/"):
                return _JsonResponse({"id": 9, "orders": [{"id": 1}, {"id": 2}], "extra": "x"})
            return _JsonResponse({"receiver": {"cost": 260, "discounts": []}, "gross_amount": 260})

        self.integration.request = fake_request

    def test_shipment_costs_are_requested_once(self):
        first = self.integration.get_shipment_costs("48196518212")
        second = self.integration.get_shipment_costs("48196518212")

        self.assertEqual(first["receiver"]["cost"], 260)
        self.assertEqual(second, {"receiver": {"cost": 260}})
        self.assertEqual(self.calls, ["/shipments/48196518212/costs"])

    def test_pack_orders_are_requested_once(self):
        self.integration.get_pack("9")
        cached = self.integration.get_pack("9")

        self.assertEqual(cached["orders"], [{"id": 1}, {"id": 2}])
        self.assertEqual(self.calls, ["/packs/9"])

    def test_without_cache_always_queries_and_refreshes(self):
        self.integration.get_shipment_costs("1")
        self.integration.get_shipment_costs("1", use_cache=False)

        self.assertEqual(self.calls, ["/shipments/1/costs", "/shipments/1/costs"])


if __name__ == "__main__":
    unittest.main()
