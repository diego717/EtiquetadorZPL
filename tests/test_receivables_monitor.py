import asyncio
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))

import receivables_endpoints as endpoints
import receivables_monitor as monitor_module
import today_endpoints
from account_statement_pdf import generate_statement_pdf
from receivables_monitor import (
    ReceivablesMonitor,
    bucket_for,
    build_clients,
    build_invoice_rows,
    build_uninvoiced,
    format_money,
    normalize_config,
    summarize,
    whatsapp_number,
)

TODAY = date(2026, 10, 6)


def url_for(model, record_id):
    return f"https://odoo.test/{model}/{record_id}"


def _move(move_id, partner_id, due, residual, currency="UYU", residual_company=None, move_type="out_invoice", contact_id=None):
    name = f"Cliente {partner_id}"
    return {
        "id": move_id,
        "name": f"A-{move_id}",
        "move_type": move_type,
        "partner_id": [contact_id or partner_id, name],
        "commercial_partner_id": [partner_id, name],
        "invoice_date": due,
        "invoice_date_due": due,
        "amount_total": residual,
        "amount_residual": residual,
        "amount_residual_signed": residual if residual_company is None else residual_company,
        "currency_id": [1, currency],
        "invoice_payment_term_id": [2, "30 Days"],
        "invoice_user_id": [3, "Vendedor"],
        "payment_state": "not_paid",
    }


class TestPureFunctions(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual([bucket_for(d) for d in (-5, 0, 1, 30, 31, 61, 91, 181)],
                         ["por_vencer", "por_vencer", "d1_30", "d1_30", "d31_60", "d61_90", "d91_180", "d180"])

    def test_whatsapp_only_accepts_uruguayan_mobiles(self):
        self.assertEqual(whatsapp_number("099 123 456"), "59899123456")
        self.assertEqual(whatsapp_number("+598 94 094 172"), "59894094172")
        self.assertEqual(whatsapp_number("26000707, 094047610"), "59894047610")
        self.assertEqual(whatsapp_number("26000707"), "")
        self.assertEqual(whatsapp_number(False, "", None), "")

    def test_money_format_uses_uruguayan_separators(self):
        self.assertEqual(format_money(1234567.5), "$ 1.234.567,50")
        self.assertEqual(format_money(-12, "USD"), "-US$ 12,00")

    def test_clients_aggregate_buckets_refunds_and_currencies(self):
        invoices = build_invoice_rows(
            [
                _move(1, 10, "2026-09-01", 1000.0),                      # 35 dias
                _move(2, 10, "2026-10-20", 500.0),                       # por vencer
                _move(3, 10, "2026-01-01", 100.0, "USD", 4000.0),        # +180
                _move(4, 10, "2026-09-01", 200.0, move_type="out_refund", residual_company=-200.0),
                _move(5, 20, "2026-10-01", 50.0),
            ],
            TODAY,
            url_for,
        )
        partners = {10: {"name": "Cliente 10", "vat": "211111110011", "mobile": "099123456", "phone": "", "email": "a@b.uy"}}
        clients = build_clients(invoices, partners, {10: {"date": "2026-09-20", "amount": 300, "currency": "UYU"}},
                                normalize_config({}), "Aramid", url_for)
        first = clients[0]
        self.assertEqual(first["partner_id"], 10)
        self.assertEqual(first["overdue"], 5000.0)
        self.assertEqual(first["buckets"]["d31_60"], 1000.0)
        self.assertEqual(first["buckets"]["d180"], 4000.0)
        self.assertEqual(first["buckets"]["por_vencer"], 500.0)
        self.assertEqual(first["credits"], -200.0)
        self.assertEqual(first["balance"], 5300.0)
        self.assertEqual(first["overdue_by_currency"], {"UYU": 1000.0, "USD": 100.0})
        self.assertEqual(first["oldest_due_date"], "2026-01-01")
        self.assertEqual(first["last_payment_date"], "2026-09-20")
        self.assertTrue(first["whatsapp_url"].startswith("https://wa.me/59899123456?text="))
        self.assertIn("US$ 100,00 y $ 1.000,00", first["whatsapp_message"])
        self.assertIn("01/01/2026", first["whatsapp_message"])
        # Sin celular no hay boton de WhatsApp.
        self.assertEqual(clients[1]["whatsapp_url"], "")

    def test_bad_template_falls_back_to_default(self):
        invoices = build_invoice_rows([_move(1, 10, "2026-09-01", 10.0)], TODAY, url_for)
        clients = build_clients(invoices, {10: {"mobile": "099123456"}}, {},
                                normalize_config({"whatsapp_template": "Hola {desconocida}"}), "Aramid", url_for)
        self.assertIn("Aramid", clients[0]["whatsapp_message"])

    def test_uninvoiced_marks_stale_orders(self):
        rows = build_uninvoiced(
            [
                {"id": 1, "name": "S1", "date_order": "2026-10-01 10:00:00", "partner_id": [5, "X"], "amount_total": 100, "amount_to_invoice": 40, "currency_id": [1, "UYU"]},
                {"id": 2, "name": "S2", "date_order": "2024-01-01 10:00:00", "partner_id": [5, "X"], "amount_total": 100, "currency_id": [1, "UYU"]},
            ],
            TODAY, 180, url_for,
        )
        self.assertEqual([(r["name"], r["stale"]) for r in rows], [("S1", False), ("S2", True)])
        self.assertEqual(rows[0]["amount_to_invoice"], 40.0)
        self.assertEqual(rows[1]["amount_to_invoice"], 100.0)

    def test_uninvoiced_skips_orders_with_nothing_to_bill(self):
        rows = build_uninvoiced(
            [
                {"id": 1, "name": "S0", "date_order": "2026-10-01", "amount_total": 100, "amount_to_invoice": 0, "currency_id": [1, "UYU"]},
                {"id": 2, "name": "SN", "date_order": "2026-10-01", "amount_total": 100, "amount_to_invoice": -50, "currency_id": [1, "UYU"]},
            ],
            TODAY, 180, url_for,
        )
        self.assertEqual(rows, [])

    def test_summary_counts_this_week(self):
        invoices = build_invoice_rows(
            [_move(1, 10, "2026-10-02", 100.0), _move(2, 10, "2026-10-10", 50.0), _move(3, 10, "2026-08-01", 10.0)],
            TODAY, url_for,
        )
        clients = build_clients(invoices, {}, {}, normalize_config({}), "", url_for)
        summary = summarize(clients, invoices, [], TODAY)
        self.assertEqual(summary["newly_overdue_count"], 1)
        self.assertEqual(summary["newly_overdue_amount"], 100.0)
        self.assertEqual(summary["due_this_week_count"], 1)
        self.assertEqual(summary["total_overdue"], 110.0)

    def test_statement_pdf_paginates_long_accounts(self):
        invoices = build_invoice_rows([_move(i, 10, "2025-01-01", 10.0) for i in range(1, 120)], TODAY, url_for)
        clients = build_clients(invoices, {10: {"vat": "1"}}, {}, normalize_config({}), "Aramid", url_for)
        pdf = generate_statement_pdf(clients[0], invoices, "Aramid", TODAY.isoformat())
        self.assertTrue(pdf.startswith(b"%PDF"))
        import fitz

        with fitz.open(stream=pdf, filetype="pdf") as document:
            self.assertGreater(document.page_count, 2)
            self.assertIn("Página 1 de", document[0].get_text())


class _FakeOdoo:
    def is_configured(self):
        return True

    def humanize_exception(self, exc):
        return str(exc)

    def record_url(self, model, record_id):
        return url_for(model, record_id)

    def get_receivables_data(self, payments_since):
        return {
            "moves": [_move(1, 10, "2026-09-01", 1000.0), _move(2, 20, "2026-10-30", 30.0)],
            "partners": {10: {"name": "Cliente 10", "mobile": "099123456"}},
            "last_payments": {},
            "company_name": "Aramid",
        }

    def get_uninvoiced_sale_orders(self):
        return [{"id": 7, "name": "S7", "date_order": "2026-10-01 10:00:00", "partner_id": [10, "Cliente 10"], "amount_total": 10, "currency_id": [1, "UYU"]}]


class TestMonitorAndEndpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self.patcher = patch.object(monitor_module, "_resolve_state_path", lambda name: tmp_path / name)
        self.patcher.start()
        self.monitor = ReceivablesMonitor(odoo=_FakeOdoo())
        self.monitor.refresh(today=TODAY)

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_client_views_and_statement(self):
        with patch.object(endpoints, "receivables_monitor", self.monitor):
            overdue = asyncio.run(endpoints.list_clients(search="", view="overdue", min_days=0, limit=300))
            balance = asyncio.run(endpoints.list_clients(search="", view="balance", min_days=0, limit=300))
            old_only = asyncio.run(endpoints.list_clients(search="", view="overdue", min_days=60, limit=300))
            response = asyncio.run(endpoints.get_statement(10))
            uninvoiced = asyncio.run(endpoints.list_uninvoiced(search="", view="recent", limit=500))
        self.assertEqual([c["partner_id"] for c in overdue["items"]], [10])
        self.assertEqual(len(balance["items"]), 2)
        self.assertEqual(old_only["items"], [])
        self.assertTrue(response.body.startswith(b"%PDF"))
        self.assertEqual(uninvoiced["total"], 1)

    def test_unknown_client_statement_is_404(self):
        from fastapi import HTTPException

        with patch.object(endpoints, "receivables_monitor", self.monitor):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(endpoints.get_statement(999))
        self.assertEqual(raised.exception.status_code, 404)

    def test_today_summary_isolates_failing_sections(self):
        def broken():
            raise ValueError("Odoo caido")

        with patch.object(today_endpoints, "_odoo_section", lambda force: broken()), patch.object(
            today_endpoints, "_shipments_section", broken
        ), patch("receivables_monitor.receivables_monitor", self.monitor):
            result = asyncio.run(today_endpoints.summary())
        self.assertFalse(result["odoo"]["ok"])
        self.assertIn("Odoo caido", result["odoo"]["error"])
        self.assertFalse(result["shipments"]["ok"])
        self.assertTrue(result["receivables"]["ok"])
        self.assertEqual(result["receivables"]["top_clients"][0]["partner_id"], 10)


if __name__ == "__main__":
    unittest.main()
