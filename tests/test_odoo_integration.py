import sys
import unittest
import xmlrpc.client
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from odoo_integration import OdooIntegration


class _FakeResponse:
    def __init__(self, content: bytes, content_type: str = "application/pdf", status_code: int = 200):
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.status_code = status_code
        self.text = content.decode("utf-8", errors="replace")


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self.response = response
        self.closed = False
        self.last_url = None
        self.last_timeout = None

    def __enter__(self):
        raise RuntimeError("Cannot open a client instance more than once.")

    def get(self, url: str, timeout: int = 0):
        self.last_url = url
        self.last_timeout = timeout
        return self.response

    def close(self):
        self.closed = True


class _FakeOdooModels:
    def __init__(self):
        self.invoice_domain = None

    def execute_kw(self, _db, _uid, _password, model, method, args, kwargs=None):
        if model == "account.move" and method == "fields_get":
            return {
                "invoice_date": {},
                "payment_state": {},
                "invoice_payment_term_id": {},
                "amount_untaxed": {},
            }
        if model == "account.payment.term" and method == "search_read":
            return [
                {"id": 1, "name": "Immediate Payment"},
                {"id": 4, "name": "30 Days"},
            ]
        if model == "account.move" and method == "search_read":
            self.invoice_domain = args[0]
            return [
                {
                    "id": 100,
                    "name": "e-Factura 100",
                    "partner_id": [5, "Cliente"],
                    "amount_total": 100.0,
                    "currency_id": [46, "UYU"],
                    "invoice_date": "2026-08-11",
                    "payment_state": "not_paid",
                    "invoice_payment_term_id": [1, "Immediate Payment"],
                    "amount_untaxed": 81.97,
                }
            ]
        raise AssertionError(f"Llamada Odoo inesperada: {model}.{method}")


class _PaidInvoiceModels:
    def execute_kw(self, _db, _uid, _password, model, method, _args, kwargs=None):
        if model == "account.move" and method == "fields_get":
            return {"payment_state": {}}
        if model == "account.move" and method == "read":
            return [{"id": 100, "name": "e-Factura 100", "payment_state": "paid"}]
        raise AssertionError(f"No se debia ejecutar {model}.{method} para una factura pagada")


class _DifferentAmountInvoiceModels:
    def execute_kw(self, _db, _uid, _password, model, method, _args, kwargs=None):
        if model == "account.move" and method == "fields_get":
            return {"payment_state": {}, "amount_total": {}, "amount_residual": {}}
        if model == "account.move" and method == "read":
            return [
                {
                    "id": 100,
                    "name": "e-Factura A-49877",
                    "amount_total": 1649.68,
                    "payment_state": "not_paid",
                }
            ]
        raise AssertionError(f"No se debia ejecutar {model}.{method} si el importe no coincide")


class _RoundingInvoiceModels:
    def __init__(self):
        self.created_values = None
        self.read_count = 0

    def execute_kw(self, _db, _uid, _password, model, method, args, kwargs=None):
        if model == "account.move" and method == "fields_get":
            return {"payment_state": {}, "amount_total": {}, "amount_residual": {}}
        if model == "account.move" and method == "read":
            self.read_count += 1
            return [{
                "id": 100,
                "name": "e-Ticket A-30277",
                "amount_total": 1292.02,
                "amount_residual": 1292.02,
                "payment_state": "not_paid" if self.read_count == 1 else "in_payment",
            }]
        if model == "account.payment.register" and method == "create":
            self.created_values = args[0]
            return 900
        if model == "account.payment.register" and method == "action_create_payments":
            return {"type": "ir.actions.act_window_close"}
        if model == "account.payment" and method == "search_read":
            return [{"id": 950}]
        raise AssertionError(f"Llamada Odoo inesperada: {model}.{method}")


class _AttachmentModels:
    def __init__(self):
        self.attachment_id = None
        self.attachment_create_count = 0
        self.attachment_values = None

    def execute_kw(self, _db, _uid, _password, model, method, args, kwargs=None):
        if model == "ir.attachment" and method == "search":
            return [self.attachment_id] if self.attachment_id else []
        if model == "ir.attachment" and method == "create":
            self.attachment_create_count += 1
            self.attachment_values = args[0]
            self.attachment_id = 700
            return self.attachment_id
        raise AssertionError(f"Llamada Odoo inesperada: {model}.{method}")


class TestOdooIntegration(unittest.TestCase):
    def test_download_sale_order_report_pdf_reuses_authenticated_session_without_context_manager(self):
        integration = OdooIntegration()
        integration.config["report_name"] = "sale.report_saleorder"
        integration._build_runtime_config = lambda auth_override=None: {}
        integration._base_url = lambda runtime=None: "http://odoo.test"

        session = _FakeSession(_FakeResponse(b"%PDF-1.4 fake"))
        integration._web_auth_session = lambda auth_override=None: session

        pdf_bytes = integration.download_sale_order_report_pdf(order_id=123)

        self.assertEqual(pdf_bytes, b"%PDF-1.4 fake")
        self.assertEqual(session.last_url, "http://odoo.test/report/pdf/sale.report_saleorder/123")
        self.assertEqual(session.last_timeout, 60)
        self.assertTrue(session.closed)

    def test_find_invoices_can_filter_pending_cash_sales_without_fixed_term_id(self):
        integration = OdooIntegration()
        models = _FakeOdooModels()
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        invoices = integration.find_invoiced_sales(
            "2026-08-11",
            "2026-08-13",
            only_pending=True,
            only_cash_payment_term=True,
        )

        self.assertEqual(len(invoices), 1)
        self.assertIn(("payment_state", "in", ["not_paid", "partial"]), models.invoice_domain)
        self.assertIn(("invoice_payment_term_id", "in", [1]), models.invoice_domain)

    def test_register_payment_rejects_invoice_that_is_already_paid(self):
        integration = OdooIntegration()
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: _PaidInvoiceModels()

        with self.assertRaisesRegex(ValueError, "ya figura como 'paid'"):
            integration.register_invoice_payment(
                invoice_id=100,
                amount=270,
                payment_date="2026-08-12",
                journal_id=3,
            )

    def test_pos_payment_rejects_different_invoice_total_before_creating_wizard(self):
        integration = OdooIntegration()
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: _DifferentAmountInvoiceModels()

        with self.assertRaisesRegex(ValueError, "no coincide con el total"):
            integration.register_invoice_payment(
                invoice_id=100,
                amount=1650,
                payment_date="2026-08-10",
                journal_id=3,
                require_exact_invoice_total=True,
            )

    def test_pos_payment_posts_rounding_difference_to_selected_account(self):
        integration = OdooIntegration()
        models = _RoundingInvoiceModels()
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
            "username": "vale@example.com",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        result = integration.register_invoice_payment(
            invoice_id=100,
            amount=1292,
            payment_date="2026-08-13",
            journal_id=104,
            memo="TotalNet Ticket 775",
            require_exact_invoice_total=True,
            rounding_account_id=586,
            rounding_source_amount=1292.02,
        )

        self.assertEqual(models.created_values["amount"], 1292.0)
        self.assertEqual(models.created_values["payment_difference_handling"], "reconcile")
        self.assertEqual(models.created_values["writeoff_account_id"], 586)
        self.assertEqual(models.created_values["writeoff_label"], "Redondeo cobro POS TotalNet")
        self.assertEqual(result["payment_id"], 950)

    def test_pos_payment_id_lookup_failure_does_not_fail_the_payment(self):
        integration = OdooIntegration()
        models = _RoundingInvoiceModels()
        original_execute_kw = models.execute_kw

        def execute_kw_without_payment_lookup(_db, _uid, _password, model, method, args, kwargs=None):
            if model == "account.payment" and method == "search_read":
                raise xmlrpc.client.Fault(1, "Invalid field 'reconciled_invoice_ids'")
            return original_execute_kw(_db, _uid, _password, model, method, args, kwargs)

        models.execute_kw = execute_kw_without_payment_lookup
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        result = integration.register_invoice_payment(
            invoice_id=100,
            amount=1292.02,
            payment_date="2026-08-13",
            journal_id=104,
        )

        self.assertIsNone(result["payment_id"])

    def test_pos_payment_rejects_unrelated_fractional_amount_as_rounding(self):
        integration = OdooIntegration()
        models = _RoundingInvoiceModels()
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        with self.assertRaisesRegex(ValueError, "no corresponde al total Odoo"):
            integration.register_invoice_payment(
                invoice_id=100,
                amount=1292,
                payment_date="2026-08-13",
                journal_id=104,
                require_exact_invoice_total=True,
                rounding_account_id=584,
                rounding_source_amount=1291.51,
            )

        self.assertIsNone(models.created_values)

    def test_totalnet_pdf_attachment_is_idempotent_per_payment_and_filename(self):
        integration = OdooIntegration()
        models = _AttachmentModels()
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        args = {
            "payment_id": 950,
            "filename": "TotalNet_Fact_30277_Ticket_775_Cupon_931583957.pdf",
            "pdf_bytes": b"%PDF-1.7 fake",
        }
        first = integration.attach_totalnet_receipt_to_payment(**args)
        second = integration.attach_totalnet_receipt_to_payment(**args)

        self.assertEqual(first["attachment_id"], second["attachment_id"])
        self.assertEqual(models.attachment_create_count, 1)
        self.assertEqual(models.attachment_values["mimetype"], "application/pdf")

    def test_resolve_operator_auth_exact_never_falls_back_to_another_user(self):
        integration = OdooIntegration()
        integration.config["operator_odoo_users"] = {
            "gianfranco": {
                "odoo_username": "gianfranco@example.com",
                "odoo_password": "secret",
            }
        }

        self.assertIsNone(integration.resolve_operator_auth_exact("vale"))
        self.assertEqual(
            integration.resolve_operator_auth_exact("GIANFRANCO"),
            {"username": "gianfranco@example.com", "password": "secret"},
        )


if __name__ == "__main__":
    unittest.main()
