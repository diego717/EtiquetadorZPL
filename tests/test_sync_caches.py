import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "api"))

import administrado_endpoints as endpoints  # noqa: E402
import odoo_integration as odoo_module  # noqa: E402
from administrado_integration import AdministradoIntegration  # noqa: E402


def _sales(count):
    return [{"envio_id": str(index), "print_mode": "imprimir"} for index in range(count)]


class TestAdministradoSalesCache(unittest.TestCase):
    def setUp(self):
        self.integration = AdministradoIntegration()
        self.integration.invalidate_sales_cache()
        self.fetches = []

        def fake_fetch(limit=20):
            self.fetches.append(limit)
            return _sales(min(limit, 5))

        self.integration._fetch_label_links = fake_fetch

    def test_repeated_requests_share_one_download(self):
        first = self.integration.list_label_links(20)
        second = self.integration.list_label_links(20)

        self.assertEqual(self.fetches, [20])
        self.assertEqual(first, second)
        second[0]["print_mode"] = "modificado"
        self.assertEqual(self.integration.list_label_links(20)[0]["print_mode"], "imprimir")

    def test_cache_expires(self):
        self.integration.list_label_links(20)
        # El reloj de Windows avanza de a ~15 ms: un TTL negativo vence siempre.
        self.integration.SALES_CACHE_TTL_SECONDS = -1.0
        self.integration.list_label_links(20)

        self.assertEqual(self.fetches, [20, 20])

    def test_downloading_a_label_invalidates_the_list(self):
        self.integration.list_label_links(20)

        class _Response:
            status_code = 200
            headers = {"Content-Type": "application/pdf"}
            content = b"%PDF-1.4"

        self.integration.request = lambda *args, **kwargs: _Response()
        try:
            self.integration.download_label_pdf("123")
        except Exception:
            pass
        self.integration.list_label_links(20)

        self.assertEqual(self.fetches, [20, 20])

    def test_worker_bypasses_cache(self):
        self.integration.list_label_links(20)
        self.integration.list_label_links(20, use_cache=False)

        self.assertEqual(self.fetches, [20, 20])

    def test_bigger_truncated_list_is_not_served_from_smaller_cache(self):
        self.integration._fetch_label_links = lambda limit=20: self.fetches.append(limit) or _sales(limit)
        self.integration.list_label_links(5)
        self.integration.list_label_links(3)
        self.integration.list_label_links(10)

        self.assertEqual(self.fetches, [5, 10])

    def test_list_fetched_during_a_print_is_not_cached(self):
        started = threading.Event()
        release = threading.Event()

        def slow_fetch(limit=20):
            self.fetches.append(limit)
            started.set()
            release.wait(2)
            return _sales(3)

        self.integration._fetch_label_links = slow_fetch
        worker = threading.Thread(target=self.integration.list_label_links, args=(20,))
        worker.start()
        started.wait(2)
        self.integration.invalidate_sales_cache()
        release.set()
        worker.join(2)
        self.integration._fetch_label_links = lambda limit=20: self.fetches.append(limit) or _sales(3)
        self.integration.list_label_links(20)

        self.assertEqual(self.fetches, [20, 20])


class TestOdooMetadataCache(unittest.TestCase):
    def setUp(self):
        odoo_module.clear_metadata_cache()
        self.addCleanup(odoo_module.clear_metadata_cache)

    def test_fields_get_is_requested_once_but_reads_are_not_cached(self):
        calls = []

        class _Proxy:
            def execute_kw(self, *args):
                calls.append(args[4])
                return {"name": {"type": "char"}} if args[4] == "fields_get" else [{"id": 1}]

        proxy = odoo_module._CachingModelsProxy(_Proxy(), "https://odoo.test")
        for _ in range(2):
            proxy.execute_kw("db", 7, "pw", "sale.order", "fields_get", [[], ["type"]])
            proxy.execute_kw("db", 7, "pw", "sale.order", "search_read", [[]], {})

        self.assertEqual(calls, ["fields_get", "search_read", "search_read"])

    def test_authenticate_is_cached_per_credentials_and_test_connection_skips_it(self):
        integration = odoo_module.OdooIntegration()
        runtime = {"base_url": "https://odoo.test", "database": "db", "username": "u", "password": "p1"}
        integration._build_runtime_config = lambda auth_override=None: dict(runtime)
        logins = []

        class _Common:
            def authenticate(self, db, username, password, context):
                logins.append(password)
                return 7

        integration._xmlrpc_common = lambda runtime=None: _Common()
        integration._authenticate()
        integration._authenticate()
        runtime["password"] = "p2"
        integration._authenticate()
        integration._authenticate(use_cache=False)

        self.assertEqual(logins, ["p1", "p2", "p2"])


class TestStockStatusCache(unittest.TestCase):
    def setUp(self):
        with endpoints.ODOO_STOCK_CACHE_LOCK:
            endpoints.ODOO_STOCK_CACHE.clear()

    def test_stock_status_is_reused_and_dropped_after_printing(self):
        queried = []

        class _Odoo:
            config = {"enabled": True}

            def is_configured(self):
                return True

            def get_sale_order_stock_statuses(self, envio_ids):
                queried.append(list(envio_ids))
                return {envio: {"code": "ready", "label": "Listo", "pickings": []} for envio in envio_ids}

        with patch.object(endpoints, "odoo_integration", _Odoo()), patch.object(
            endpoints, "_save_print_state", lambda state: None
        ):
            endpoints._attach_odoo_stock_statuses(_sales(2))
            endpoints._attach_odoo_stock_statuses(_sales(3))
            endpoints._record_print_event(envio_id="0", mode="imprimir", success=True)
            result = endpoints._attach_odoo_stock_statuses(_sales(3))

        self.assertEqual(queried, [["0", "1"], ["2"], ["0"]])
        self.assertEqual(result[0]["odoo_stock"]["code"], "ready")


if __name__ == "__main__":
    unittest.main()
