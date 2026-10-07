import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from administrado_integration import AdministradoIntegration


class TestAdministradoSync(unittest.TestCase):
    def test_list_label_links_prefers_requests_before_playwright(self):
        integration = AdministradoIntegration()
        integration.config["cookie_header"] = "test-cookie"
        integration.config["use_playwright"] = True

        expected = [{"envio_id": "123", "print_mode": "imprimir"}]
        integration._list_label_links_via_requests = lambda limit=20: (expected, True)
        integration.list_label_links_playwright = lambda limit=20: self.fail("No deberia usar Playwright")

        result = integration.list_label_links(limit=20)

        self.assertEqual(result, expected)


class TestMergePrintState(unittest.TestCase):
    def _merge(self, sales, shipments):
        from api import administrado_endpoints

        original = administrado_endpoints._load_print_state
        administrado_endpoints._load_print_state = lambda: {"shipments": shipments, "history": []}
        try:
            return administrado_endpoints._merge_print_state_into_sales(sales)
        finally:
            administrado_endpoints._load_print_state = original

    def test_label_printed_directly_in_administrado_is_not_reverted_by_local_history(self):
        # Se intento solo etiqueta desde la app (queda "imprimir") y despues se imprimio en Administrado.
        sales = [{"envio_id": "48127662238", "print_mode": "reimprimir"}]
        shipments = {"48127662238": {"print_mode": "imprimir", "last_print_result": "Solo etiqueta"}}

        result = self._merge(sales, shipments)

        self.assertEqual(result[0]["print_mode"], "reimprimir")

    def test_print_from_app_marks_reprint_before_administrado_reflects_it(self):
        sales = [{"envio_id": "48121795258", "print_mode": "imprimir"}]
        shipments = {"48121795258": {"print_mode": "reimprimir", "last_print_result": "Orden + etiqueta"}}

        result = self._merge(sales, shipments)

        self.assertEqual(result[0]["print_mode"], "reimprimir")


class TestOdooStockEnrichment(unittest.TestCase):
    def test_stock_status_is_attached_without_filtering_sales(self):
        from api import administrado_endpoints

        fake_odoo = Mock()
        fake_odoo.config = {"enabled": True}
        fake_odoo.is_configured.return_value = True
        fake_odoo.get_sale_order_stock_statuses.return_value = {
            "481": {"code": "waiting", "label": "Pendiente de stock", "detail": "Falta reservar"}
        }
        sales = [{"envio_id": "481"}, {"envio_id": "482"}]

        with patch.object(administrado_endpoints, "odoo_integration", fake_odoo):
            result = administrado_endpoints._attach_odoo_stock_statuses(sales)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["odoo_stock"]["code"], "waiting")
        self.assertEqual(result[1]["odoo_stock"]["code"], "unknown")

    def test_stock_lookup_error_is_informative_and_does_not_raise(self):
        from api import administrado_endpoints

        fake_odoo = Mock()
        fake_odoo.config = {"enabled": True}
        fake_odoo.is_configured.return_value = True
        fake_odoo.get_sale_order_stock_statuses.side_effect = ValueError("sin permiso stock.picking")
        fake_odoo.humanize_exception.return_value = "sin permiso stock.picking"
        sales = [{"envio_id": "481"}]

        with patch.object(administrado_endpoints, "odoo_integration", fake_odoo):
            result = administrado_endpoints._attach_odoo_stock_statuses(sales)

        self.assertEqual(result[0]["odoo_stock"]["code"], "error")
        self.assertIn("sin permiso", result[0]["odoo_stock"]["detail"])


class TestPrintChatterIntegration(unittest.TestCase):
    def test_chatter_failure_does_not_turn_successful_print_into_failure(self):
        from api import administrado_endpoints

        fake_odoo = Mock()
        fake_odoo.config = {
            "username": "integracion@example.com",
            "confirm_order_on_print": False,
            "automation_order_to_label_delay_seconds": 0,
        }
        fake_odoo.resolve_operator_auth.return_value = None
        fake_odoo.find_sale_order_by_envio.return_value = {"id": 10, "name": "ML 481"}
        fake_odoo.post_sale_order_print_note.side_effect = ValueError("sin permiso chatter")
        fake_odoo.humanize_exception.return_value = "sin permiso chatter"
        request = administrado_endpoints.AdministradoShipmentPrintRequest(
            envio_id="481",
            mode="both",
            operation_id="print-test",
        )

        with patch.object(administrado_endpoints, "odoo_integration", fake_odoo), patch.object(
            administrado_endpoints,
            "_print_order_with_fallback",
            return_value={"success": True, "printer": "Epson"},
        ), patch.object(
            administrado_endpoints,
            "_print_label_with_fallback",
            return_value={"success": True, "printer": "Godex"},
        ), patch.object(administrado_endpoints, "_record_print_event"):
            result = asyncio.run(administrado_endpoints.print_shipment(request))

        self.assertTrue(result["success"])
        self.assertFalse(result["odoo_note_result"]["success"])
        self.assertIn("sin permiso", result["odoo_note_result"]["error"])
        fake_odoo.post_sale_order_print_note.assert_called_once()


if __name__ == "__main__":
    unittest.main()
