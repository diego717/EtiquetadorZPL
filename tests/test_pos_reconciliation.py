import sys
import unittest
from datetime import date, timedelta
from pathlib import Path


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import pos_reconciliation as reconciliation


class TestPosReconciliation(unittest.TestCase):
    def test_totalnet_date_is_normalized_for_odoo_payment_wizard(self):
        self.assertEqual(
            reconciliation.normalize_date_iso("14/08/2026"),
            "2026-08-14",
        )

    def test_settlement_query_range_extends_forward_by_lookahead_days(self):
        date_to = (date.today() - timedelta(days=20)).isoformat()
        settlement_from, settlement_to = reconciliation.resolve_settlement_query_range(
            "2026-01-01", date_to, lookahead_days=5
        )

        self.assertEqual(settlement_from, "2026-01-01")
        self.assertEqual(
            settlement_to,
            (date.today() - timedelta(days=15)).isoformat(),
        )

    def test_settlement_query_range_never_queries_today_or_future(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _settlement_from, settlement_to = reconciliation.resolve_settlement_query_range(
            "2026-01-01", yesterday, lookahead_days=15
        )

        self.assertEqual(settlement_to, yesterday)

    def test_filter_cupones_by_transaction_date_keeps_only_requested_sale_range(self):
        cupones = [
            {"transaccion": {"cupon_id": 1, "fecha_cupon": "2026-08-05"}},
            {"transaccion": {"cupon_id": 2, "fecha_cupon": "2026-08-12"}},
            {"transaccion": {"cupon_id": 3, "fecha_cupon": "2026-08-20"}},
            {"transaccion": {"cupon_id": 4}},
        ]

        filtered = reconciliation.filter_cupones_by_transaction_date(
            cupones, "2026-08-10", "2026-08-15"
        )

        cupon_ids = {
            reconciliation._cupon_field(cupon, "transaccion.cupon_id") for cupon in filtered
        }
        self.assertEqual(cupon_ids, {2, 4})

    def test_payment_rounding_uses_half_up_rule(self):
        self.assertEqual(reconciliation.round_payment_amount("1292.02"), 1292.0)
        self.assertEqual(reconciliation.round_payment_amount("1292.49"), 1292.0)
        self.assertEqual(reconciliation.round_payment_amount("1292.50"), 1293.0)
        self.assertEqual(reconciliation.round_payment_amount("1292.99"), 1293.0)

    def test_totalnet_numeric_uyu_code_matches_odoo_uyu_invoice(self):
        coupon = {
            "transaccion": {
                "cupon_id": 1,
                "importe": 917.39,
                "moneda": 858,
                "fecha_cupon": "2026-08-11",
            }
        }
        invoice = {
            "id": 10,
            "name": "e-Factura 10",
            "amount_total": 917.39,
            "currency_id": [46, "UYU"],
            "invoice_date": "2026-08-11",
        }

        result = reconciliation.match_cupones_to_invoices([coupon], [invoice])

        self.assertEqual(len(result["matches_unicos"]), 1)
        self.assertEqual(result["matches_unicos"][0]["cupon"]["moneda"], "UYU")
        self.assertEqual(result["matches_unicos"][0]["cupon"]["moneda_original"], 858)
        self.assertEqual(result["sin_match"], [])

    def test_numeric_currency_codes_do_not_cross_uyu_with_usd(self):
        coupon = {
            "transaccion": {
                "cupon_id": 1,
                "importe": 100,
                "moneda": 840,
                "fecha_cupon": "2026-08-11",
            }
        }
        invoice = {
            "id": 10,
            "amount_total": 100,
            "currency_id": [46, "UYU"],
            "invoice_date": "2026-08-11",
        }

        result = reconciliation.match_cupones_to_invoices([coupon], [invoice])

        self.assertEqual(result["matches_unicos"], [])
        self.assertEqual(result["sin_match"][0]["amount_candidates"], [])

    def test_paid_invoice_is_visible_but_cannot_register_another_payment(self):
        coupon = {
            "transaccion": {
                "cupon_id": 1,
                "importe": 270,
                "moneda": 858,
                "fecha_cupon": "2026-08-12",
            }
        }
        invoice = {
            "id": 10,
            "name": "e-Factura 10",
            "amount_total": 270,
            "currency_id": [46, "UYU"],
            "invoice_date": "2026-08-12",
            "invoice_payment_state": "paid",
        }

        result = reconciliation.match_cupones_to_invoices([coupon], [invoice])

        self.assertEqual(len(result["matches_unicos"]), 1)
        self.assertFalse(result["matches_unicos"][0]["invoice"]["can_register_payment"])

    def test_totalnet_invoice_number_has_priority_over_same_amount_invoice(self):
        coupon = {
            "transaccion": {
                "cupon_id": 771,
                "numero_factura": 49890,
                "importe": 917.39,
                "moneda": 858,
                "fecha_cupon": "2026-08-11",
            }
        }
        invoices = [
            {
                "id": 10,
                "name": "e-Factura A-49890",
                "amount_total": 917.39,
                "currency_id": [46, "UYU"],
                "invoice_date": "2026-08-11",
                "invoice_payment_state": "paid",
            },
            {
                "id": 11,
                "name": "e-Ticket A-30262",
                "amount_total": 917.39,
                "currency_id": [46, "UYU"],
                "invoice_date": "2026-08-12",
                "invoice_payment_state": "not_paid",
            },
        ]

        result = reconciliation.match_cupones_to_invoices([coupon], invoices)

        self.assertEqual(len(result["matches_unicos"]), 1)
        match = result["matches_unicos"][0]
        self.assertEqual(match["invoice"]["name"], "e-Factura A-49890")
        self.assertEqual(match["matched_by"], "numero_factura_totalnet")
        self.assertEqual(result["ambiguos"], [])

    def test_number_match_with_small_amount_difference_requires_rounding_writeoff(self):
        coupon = {
            "transaccion": {
                "cupon_id": 770,
                "numero_factura": 49877,
                "importe": 1650,
                "moneda": 858,
                "fecha_cupon": "2026-08-10",
            }
        }
        invoice = {
            "id": 10,
            "name": "e-Factura A-49877",
            "amount_total": 1649.68,
            "currency_id": [46, "UYU"],
            "invoice_date": "2026-08-10",
            "invoice_payment_state": "not_paid",
        }

        result = reconciliation.match_cupones_to_invoices([coupon], [invoice])

        match = result["matches_unicos"][0]
        self.assertFalse(match["amount_matches"])
        self.assertEqual(match["amount_difference"], -0.32)
        self.assertTrue(match["rounding_matches"])
        self.assertTrue(match["requires_rounding_writeoff"])
        self.assertTrue(match["can_confirm"])
        self.assertEqual(result["sin_match"], [])

    def test_payment_memo_contains_totalnet_ticket_details(self):
        coupon = {
            "transaccion.ticket": 775,
            "transaccion.autorizacion": "173868",
            "transaccion.lote": 375,
            "transaccion.numero_factura": 30277,
            "transaccion.importe": 1292.02,
            "transaccion.moneda": 858,
            "transaccion.sello": "MASTERCARD",
            "transaccion.producto": "DEBITO",
            "transaccion.terminal": "30983093",
            "transaccion.ultimos_4_Digitos": "5878",
            "transaccion.importe_devolución_impuesto": 21.18,
        }
        summary = reconciliation._cupon_summary(coupon)

        memo = reconciliation.build_payment_memo("e-Ticket A-30277", summary)

        self.assertIn("TotalNet Fact. 30277", memo)
        self.assertIn("Ticket 775", memo)
        self.assertIn("Aut. 173868", memo)
        self.assertIn("Mastercard Debito", memo)
        self.assertIn("Desc. Ley 19.210 UYU 21.18", memo)
        self.assertIn("Total cobrado UYU 1270.84", memo)
        self.assertIn("****5878", memo)
        self.assertIn("Terminal 30983093", memo)

    def test_manual_ticket_memo_only_has_ticket_and_lote(self):
        summary = {
            "manual_entry": True,
            "ticket": "0926",
            "lote": "393",
            "autorizacion": "074234",
            "numero_factura": 49947,
            "sello": "VISA",
            "producto": "DEBITO",
            "importe": 1035.0,
            "moneda": "UYU",
        }

        memo = reconciliation.build_payment_memo("e-Factura A-49947", summary)

        self.assertEqual(memo, "Ticket 0926 | Lote 393")

    def test_manual_ticket_memo_omits_lote_when_blank(self):
        summary = {"manual_entry": True, "ticket": "0926", "lote": ""}

        memo = reconciliation.build_payment_memo("e-Factura A-49947", summary)

        self.assertEqual(memo, "Ticket 0926")

    def test_exact_pending_number_match_can_be_confirmed(self):
        coupon = {
            "transaccion": {
                "cupon_id": 925,
                "numero_factura": 30300,
                "importe": 490,
                "moneda": 858,
                "fecha_cupon": "2026-08-14",
            }
        }
        invoice = {
            "id": 10,
            "name": "e-Ticket A-30300",
            "amount_total": 490,
            "currency_id": [46, "UYU"],
            "invoice_date": "2026-08-14",
            "invoice_payment_state": "not_paid",
        }

        match = reconciliation.match_cupones_to_invoices([coupon], [invoice])["matches_unicos"][0]

        self.assertTrue(match["amount_matches"])
        self.assertTrue(match["can_confirm"])

    def test_coupons_are_never_grouped_to_guess_an_invoice(self):
        coupons = [
            {"transaccion": {"cupon_id": 1, "importe": 1351, "moneda": 858, "fecha_cupon": "2026-08-12"}},
            {"transaccion": {"cupon_id": 2, "importe": 1291, "moneda": 858, "fecha_cupon": "2026-08-12"}},
        ]
        invoice = {
            "id": 10,
            "name": "e-Ticket A-30254",
            "amount_total": 2642,
            "currency_id": [46, "UYU"],
            "invoice_date": "2026-08-12",
            "invoice_payment_state": "not_paid",
        }

        result = reconciliation.match_cupones_to_invoices(coupons, [invoice])

        self.assertEqual(result["matches_unicos"], [])
        self.assertEqual(result["ambiguos"], [])
        self.assertEqual(len(result["sin_match"]), 2)

    def test_large_difference_is_not_accepted_as_rounding(self):
        coupon = {
            "transaccion": {
                "cupon_id": 772,
                "numero_factura": 49813,
                "importe": 432.64,
                "moneda": 858,
                "fecha_cupon": "2026-08-12",
            }
        }
        invoice = {
            "id": 10,
            "name": "e-Factura A-49813",
            "amount_total": 423.64,
            "currency_id": [46, "UYU"],
            "invoice_date": "2026-08-12",
            "invoice_payment_state": "not_paid",
        }

        match = reconciliation.match_cupones_to_invoices([coupon], [invoice])["matches_unicos"][0]

        self.assertFalse(match["amount_matches"])
        self.assertFalse(match["rounding_matches"])
        self.assertFalse(match["can_confirm"])

    def test_reported_invoice_number_never_falls_back_to_another_same_amount_invoice(self):
        coupon = {
            "transaccion": {
                "cupon_id": 771,
                "numero_factura": 49890,
                "importe": 917.39,
                "moneda": 858,
                "fecha_cupon": "2026-08-11",
            }
        }
        transfer_invoice = {
            "id": 11,
            "name": "e-Ticket A-30262",
            "amount_total": 917.39,
            "currency_id": [46, "UYU"],
            "invoice_date": "2026-08-12",
            "invoice_payment_state": "not_paid",
        }

        result = reconciliation.match_cupones_to_invoices([coupon], [transfer_invoice])

        self.assertEqual(result["matches_unicos"], [])
        self.assertEqual(result["ambiguos"], [])
        self.assertEqual(result["sin_match"][0]["invoice_number_searched"], "49890")
        self.assertEqual(result["sin_match"][0]["amount_candidates"], [])


class TestSharedPaymentHistory(unittest.TestCase):
    def test_totalnet_and_mercadolibre_share_history_without_marking_coupons(self):
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "pos_reconciliation_state.json"
            with patch.object(reconciliation, "_resolve_state_path", return_value=state_path):
                reconciliation.mark_cupones_processed([77], [{"ok": True, "cupon_id": 77}])
                reconciliation.record_external_payments(
                    [{"ok": True, "source": "mercadolibre", "payment_id": 951}]
                )
                state = reconciliation.load_state()

        self.assertEqual(state["processed_cupon_ids"], ["77"])
        self.assertEqual(len(state["history"]), 2)
        self.assertEqual(state["history"][1]["payments"][0]["source"], "mercadolibre")

if __name__ == "__main__":
    unittest.main()
