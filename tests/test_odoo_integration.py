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


class _ProductModels:
    def __init__(self):
        self.count_domain = None
        self.read_domain = None
        self.read_kwargs = None

    def execute_kw(self, _db, _uid, _password, model, method, args, kwargs=None):
        if model == "product.product" and method == "fields_get":
            return {
                "name": {},
                "display_name": {},
                "default_code": {},
                "barcode": {},
                "product_tmpl_id": {},
                "uom_id": {},
                "categ_id": {},
                "active": {},
                "detailed_type": {},
                "lst_price": {},
                "qty_available": {},
                "virtual_available": {},
                "incoming_qty": {},
                "outgoing_qty": {},
            }
        if model == "product.product" and method == "search_count":
            self.count_domain = args[0]
            return 1
        if model == "product.product" and method == "search_read":
            self.read_domain = args[0]
            self.read_kwargs = kwargs or {}
            return [
                {
                    "id": 55,
                    "name": "Etiqueta Premium",
                    "display_name": "[ETI-001] Etiqueta Premium",
                    "default_code": "ETI-001",
                    "barcode": "779000000001",
                    "product_tmpl_id": [12, "Etiqueta Premium"],
                    "uom_id": [1, "Units"],
                    "categ_id": [8, "Etiquetas"],
                    "active": True,
                    "detailed_type": "product",
                    "lst_price": 120.5,
                    "qty_available": 9,
                    "virtual_available": 7,
                    "incoming_qty": 2,
                    "outgoing_qty": 4,
                }
            ]
        raise AssertionError(f"Llamada Odoo inesperada: {model}.{method}")


class _StockAndChatterModels:
    def __init__(self):
        self.calls = []
        self.note_kwargs = None
        self.note_bodies = []

    def execute_kw(self, _db, _uid, _password, model, method, args, kwargs=None):
        self.calls.append((model, method))
        if model == "sale.order" and method == "fields_get":
            return {
                "id": {},
                "name": {},
                "state": {},
                "client_order_ref": {},
                "origin": {},
                "picking_ids": {},
                "x_shipment_id": {},
            }
        if model == "sale.order" and method == "search_read":
            return [
                {
                    "id": 10,
                    "name": "ML 100",
                    "state": "sale",
                    "client_order_ref": "100",
                    "origin": "",
                    "picking_ids": [50],
                    "x_shipment_id": "100",
                },
                {
                    "id": 11,
                    "name": "ML 200",
                    "state": "sale",
                    "client_order_ref": "200",
                    "origin": "",
                    "picking_ids": [51],
                    "x_shipment_id": "200",
                },
                {
                    "id": 12,
                    "name": "ML 400",
                    "state": "sale",
                    "client_order_ref": "400",
                    "origin": "",
                    "picking_ids": [52],
                    "x_shipment_id": "400",
                },
            ]
        if model == "stock.picking" and method == "fields_get":
            return {
                "id": {},
                "name": {},
                "state": {},
                "sale_id": {},
                "picking_type_code": {},
                "products_availability": {},
                "products_availability_state": {},
                "scheduled_date": {},
            }
        if model == "stock.picking" and method == "search_read":
            return [
                {
                    "id": 50,
                    "name": "WH/OUT/00050",
                    "state": "assigned",
                    "sale_id": [10, "ML 100"],
                    "picking_type_code": "outgoing",
                    "products_availability": "Disponible",
                    "products_availability_state": "available",
                },
                {
                    "id": 51,
                    "name": "WH/OUT/00051",
                    "state": "confirmed",
                    "sale_id": [11, "ML 200"],
                    "picking_type_code": "outgoing",
                    "products_availability": "Faltan productos",
                    "products_availability_state": "late",
                },
                {
                    "id": 52,
                    "name": "WH/OUT/00052",
                    "state": "assigned",
                    "sale_id": [12, "ML 400"],
                    "picking_type_code": "outgoing",
                    "products_availability": "Parcialmente disponible",
                    "products_availability_state": "expected",
                },
            ]
        if model == "stock.move" and method == "fields_get":
            return {
                "id": {},
                "picking_id": {},
                "product_id": {},
                "product_uom_qty": {},
                "product_uom": {},
                "state": {},
                "reserved_availability": {},
            }
        if model == "stock.move" and method == "search_read":
            return [
                {
                    "id": 500,
                    "picking_id": [50, "WH/OUT/00050"],
                    "product_id": [70, "Producto listo"],
                    "product_uom_qty": 2,
                    "product_uom": [1, "Unidades"],
                    "state": "assigned",
                    "reserved_availability": 2,
                },
                {
                    "id": 501,
                    "picking_id": [51, "WH/OUT/00051"],
                    "product_id": [71, "Producto faltante"],
                    "product_uom_qty": 3,
                    "product_uom": [1, "Unidades"],
                    "state": "confirmed",
                    "reserved_availability": 0,
                },
                {
                    "id": 502,
                    "picking_id": [52, "WH/OUT/00052"],
                    "product_id": [72, "Producto reservado"],
                    "product_uom_qty": 1,
                    "product_uom": [1, "Unidades"],
                    "state": "assigned",
                    "reserved_availability": 1,
                },
                {
                    "id": 503,
                    "picking_id": [52, "WH/OUT/00052"],
                    "product_id": [73, "Producto sin reserva"],
                    "product_uom_qty": 2,
                    "product_uom": [2, "kg"],
                    "state": "assigned",
                    "reserved_availability": 0,
                },
            ]
        if model == "mail.message" and method == "search":
            marker = next(
                (str(term[2]) for term in args[0] if isinstance(term, tuple) and term[0] == "body"),
                "",
            )
            for index, body in enumerate(self.note_bodies, start=1):
                if marker and marker in body:
                    return [900 + index]
            return []
        if model == "sale.order" and method == "message_post":
            self.note_kwargs = kwargs or {}
            self.note_bodies.append(str(self.note_kwargs.get("body") or ""))
            return 901
        raise AssertionError(f"Llamada Odoo inesperada: {model}.{method}")


class _StockOdoo17Models(_StockAndChatterModels):
    def execute_kw(self, db, uid, password, model, method, args, kwargs=None):
        if model == "stock.move" and method == "fields_get":
            self.calls.append((model, method))
            return {
                "id": {},
                "picking_id": {},
                "product_id": {},
                "product_uom_qty": {},
                "product_uom": {},
                "state": {},
                "quantity": {},
                "picked": {},
            }
        if model == "stock.move" and method == "search_read":
            self.calls.append((model, method))
            return [{
                "id": 600,
                "picking_id": [50, "WH/OUT/00050"],
                "product_id": [80, "Producto Odoo 17"],
                "product_uom_qty": 3,
                "product_uom": [1, "Unidades"],
                "state": "assigned",
                "quantity": 3,
                "picked": False,
            }]
        return super().execute_kw(db, uid, password, model, method, args, kwargs)


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

    def test_sale_order_url_points_to_the_order_form(self):
        integration = OdooIntegration()
        integration.config["base_url"] = "https://aramid.odoo.com/"

        url = integration.sale_order_url(4521)

        self.assertEqual(url, "https://aramid.odoo.com/web#id=4521&model=sale.order&view_type=form")

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

    def test_list_products_reads_inventory_products_with_stock(self):
        integration = OdooIntegration()
        models = _ProductModels()
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        result = integration.list_products(search="eti", limit=50, offset=10)

        self.assertEqual(result["total"], 1)
        self.assertFalse(result["has_more"])
        self.assertIn(("active", "=", True), models.read_domain)
        self.assertIn(("detailed_type", "in", ["product", "consu"]), models.read_domain)
        self.assertIn(("default_code", "ilike", "eti"), models.read_domain)
        self.assertEqual(models.read_kwargs["limit"], 50)
        self.assertEqual(models.read_kwargs["offset"], 10)
        self.assertIn("qty_available", models.read_kwargs["fields"])
        self.assertEqual(result["items"][0]["default_code"], "ETI-001")
        self.assertEqual(result["items"][0]["uom"], "Units")
        self.assertEqual(result["items"][0]["category"], "Etiquetas")
        self.assertEqual(result["items"][0]["list_price"], 120.5)
        self.assertEqual(result["items"][0]["qty_available"], 9)

    def test_stock_statuses_are_loaded_in_batch_and_remain_informative(self):
        integration = OdooIntegration()
        models = _StockAndChatterModels()
        integration.config["shipment_field"] = "x_shipment_id"
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
            "order_prefix": "ML ",
            "shipment_field": "x_shipment_id",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        statuses = integration.get_sale_order_stock_statuses(["100", "200", "300", "400", "100"])

        self.assertEqual(statuses["100"]["code"], "ready")
        self.assertEqual(statuses["100"]["pickings"][0]["name"], "WH/OUT/00050")
        self.assertEqual(statuses["200"]["code"], "waiting")
        self.assertIn("Faltan productos", statuses["200"]["detail"])
        self.assertEqual(statuses["300"]["code"], "order_missing")
        self.assertEqual(statuses["400"]["code"], "partial")
        self.assertIsNone(statuses["400"]["missing_qty"])
        self.assertEqual(statuses["400"]["shortages"][0]["product"], "Producto sin reserva")
        self.assertEqual(statuses["400"]["shortages"][0]["missing_qty"], 2)
        self.assertEqual(models.calls.count(("sale.order", "search_read")), 1)
        self.assertEqual(models.calls.count(("stock.picking", "search_read")), 1)
        self.assertEqual(models.calls.count(("stock.move", "search_read")), 1)

    def test_stock_status_supports_odoo_17_quantity_field(self):
        integration = OdooIntegration()
        models = _StockOdoo17Models()
        integration.config["shipment_field"] = "x_shipment_id"
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
            "shipment_field": "x_shipment_id",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        status = integration.get_sale_order_stock_statuses(["100"])["100"]

        self.assertEqual(status["code"], "ready")
        self.assertEqual(status["reserved_qty"], 3)
        self.assertEqual(status["complete_lines"], 1)

    def test_print_note_uses_internal_chatter_without_assigning_responsible(self):
        integration = OdooIntegration()
        models = _StockAndChatterModels()
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        result = integration.post_sale_order_print_note(
            order_id=10,
            envio_id="100<script>",
            mode="both",
            order_printer="Epson & Deposito",
            label_printer="Godex <GE300>",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], 901)
        self.assertEqual(models.note_kwargs["subtype_xmlid"], "mail.mt_note")
        # Nota corta en texto plano: Odoo escapa el HTML recibido por XML-RPC.
        self.assertEqual(models.note_kwargs["body"], "Orden y etiqueta impresas")
        self.assertNotIn("partner_ids", models.note_kwargs)
        self.assertNotIn("user_id", models.note_kwargs)
        self.assertNotIn("responsable", models.note_kwargs["body"].lower())

    def test_print_note_is_idempotent_for_the_same_operation(self):
        integration = OdooIntegration()
        models = _StockAndChatterModels()
        integration._build_runtime_config = lambda auth_override=None: {
            "database": "test",
            "password": "test",
        }
        integration._authenticate = lambda auth_override=None: 7
        integration._xmlrpc_models = lambda runtime=None: models

        first = integration.post_sale_order_print_note(10, "100", "order_only", event_key="print-abc")
        second = integration.post_sale_order_print_note(10, "100", "order_only", event_key="print-abc")
        third = integration.post_sale_order_print_note(10, "100", "order_only", event_key="print-def")

        self.assertTrue(first["posted"])
        self.assertTrue(second["duplicate"])
        self.assertTrue(third["posted"])
        self.assertEqual(models.calls.count(("sale.order", "message_post")), 2)
        self.assertNotIn("ref", models.note_kwargs["body"].lower())
        self.assertEqual(models.note_kwargs["body"], "Orden impresa")


if __name__ == "__main__":
    unittest.main()
