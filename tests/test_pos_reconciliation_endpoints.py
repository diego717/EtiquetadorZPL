import asyncio
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))

import pos_reconciliation_endpoints as endpoints


class _FakeOdooIntegration:
    def __init__(self, operator_exists=True, payment_id=950):
        self.operator_exists = operator_exists
        self.payment_id = payment_id
        self.authenticated_with = None
        self.payment_calls = []
        self.attachment_calls = []
        self.invoice_search_calls = []

    def is_configured(self):
        return True

    def find_invoiced_sales(self, **kwargs):
        self.invoice_search_calls.append(dict(kwargs))
        return [
            {
                "id": 103728,
                "name": "e-Factura A-49947",
                "partner_id": [152490, "Tlenor S.A."],
                "amount_total": 1035.34,
                "amount_residual": 1035.34,
                "currency_id": [46, "UYU"],
                "invoice_date": "2026-08-17",
                "invoice_payment_term_id": [1, "Immediate Payment"],
                "invoice_origin": "S57494",
                "invoice_payment_state": "not_paid",
            }
        ]

    def get_operator_odoo_users_public(self):
        return [
            {
                "app_username": "vale",
                "odoo_username": "vale@example.com",
                "has_password": True,
            }
        ]

    def get_rounding_accounts(self):
        return [{"id": 584, "code": "550101", "name": "Redondeos"}]

    def resolve_operator_auth_exact(self, app_username):
        if self.operator_exists and app_username == "vale":
            return {"username": "vale@example.com", "password": "secret"}
        return None

    def _authenticate(self, auth_override=None):
        self.authenticated_with = dict(auth_override or {})
        return 25

    def register_invoice_payment(
        self,
        invoice_id,
        amount,
        payment_date,
        journal_id,
        memo="",
        auth_override=None,
        require_exact_invoice_total=False,
        rounding_account_id=None,
        rounding_source_amount=None,
    ):
        self.payment_calls.append(
            {
                "invoice_id": invoice_id,
                "amount": amount,
                "payment_date": payment_date,
                "journal_id": journal_id,
                "auth_override": dict(auth_override or {}),
                "require_exact_invoice_total": require_exact_invoice_total,
                "rounding_account_id": rounding_account_id,
                "rounding_source_amount": rounding_source_amount,
            }
        )
        return {
            "invoice_id": invoice_id,
            "payment_id": self.payment_id,
            "payment_state": "in_payment",
            "actor_username": auth_override["username"],
        }

    def attach_totalnet_receipt_to_payment(
        self,
        payment_id,
        filename,
        pdf_bytes,
        auth_override=None,
    ):
        self.attachment_calls.append(
            {
                "payment_id": payment_id,
                "filename": filename,
                "pdf_bytes": pdf_bytes,
                "auth_override": dict(auth_override or {}),
            }
        )
        return {"attachment_id": 700, "attachment_created": True, "filename": filename}

    def record_url(self, model, record_id):
        return f"https://odoo.example/web#id={record_id}&model={model}&view_type=form"


class TestPosReconciliationEndpoints(unittest.TestCase):
    @staticmethod
    def _request(
        operator="vale",
        journal_id=3,
        fecha="2026-08-14",
        importe=490,
        round_to_integer=False,
        rounding_account_id=None,
        attach_receipt_pdf=True,
    ):
        return endpoints.PosReconciliationConfirmRequest(
            operator_app_username=operator,
            items=[
                endpoints.ConfirmItem(
                    cupon={
                        "cupon_id": 77,
                        "importe": importe,
                        "fecha": fecha,
                        "sello": "VISA",
                    },
                    invoice_id=100,
                    invoice_name="e-Ticket A-30300",
                    journal_id=journal_id,
                    round_to_integer=round_to_integer,
                    rounding_account_id=rounding_account_id,
                    attach_receipt_pdf=attach_receipt_pdf,
                )
            ],
        )

    def test_operator_list_never_exposes_password(self):
        fake = _FakeOdooIntegration()
        with patch.object(endpoints, "odoo_integration", fake):
            result = asyncio.run(endpoints.get_payment_operators())

        self.assertTrue(result["selection_required"])
        self.assertEqual(result["items"][0]["odoo_username"], "vale@example.com")
        self.assertNotIn("password", result["items"][0])

    def test_rounding_accounts_are_loaded_from_odoo(self):
        fake = _FakeOdooIntegration()
        with patch.object(endpoints, "odoo_integration", fake):
            result = asyncio.run(endpoints.get_rounding_accounts())

        self.assertEqual(result["items"][0]["id"], 584)
        self.assertEqual(result["items"][0]["name"], "Redondeos")

    def test_confirm_uses_selected_operator_and_audits_actor(self):
        fake = _FakeOdooIntegration()
        saved_history = []

        def _capture_history(cupon_ids, results):
            saved_history.append((cupon_ids, results))

        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon, "mark_cupones_processed", _capture_history
        ):
            result = asyncio.run(endpoints.confirm(self._request()))

        expected_auth = {"username": "vale@example.com", "password": "secret"}
        self.assertEqual(fake.authenticated_with, expected_auth)
        self.assertEqual(fake.payment_calls[0]["auth_override"], expected_auth)
        self.assertTrue(fake.payment_calls[0]["require_exact_invoice_total"])
        self.assertEqual(result["operator"]["app_username"], "vale")
        self.assertEqual(result["operator"]["odoo_username"], "vale@example.com")
        self.assertEqual(result["items"][0]["actor_odoo_username"], "vale@example.com")
        self.assertEqual(saved_history[0][1][0]["operator_app_username"], "vale")
        self.assertEqual(saved_history[0][1][0]["invoice_name"], "e-Ticket A-30300")
        self.assertEqual(saved_history[0][1][0]["cupon"]["cupon_id"], 77)
        self.assertTrue(result["items"][0]["attachment_ok"])
        self.assertEqual(fake.attachment_calls[0]["auth_override"], expected_auth)
        self.assertTrue(fake.attachment_calls[0]["pdf_bytes"].startswith(b"%PDF"))

    def test_confirm_normalizes_totalnet_day_first_date_for_odoo(self):
        fake = _FakeOdooIntegration()
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon, "mark_cupones_processed", lambda *_args: None
        ):
            result = asyncio.run(endpoints.confirm(self._request(fecha="14/08/2026")))

        self.assertTrue(result["items"][0]["ok"])
        self.assertEqual(fake.payment_calls[0]["payment_date"], "2026-08-14")

    def test_confirm_rounds_payment_and_passes_selected_difference_account(self):
        fake = _FakeOdooIntegration()
        request = self._request(
            importe=1292.02,
            round_to_integer=True,
            rounding_account_id=586,
        )
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon, "mark_cupones_processed", lambda *_args: None
        ):
            result = asyncio.run(endpoints.confirm(request))

        self.assertTrue(result["items"][0]["ok"])
        self.assertEqual(fake.payment_calls[0]["amount"], 1292.0)
        self.assertEqual(fake.payment_calls[0]["rounding_account_id"], 586)
        self.assertEqual(fake.payment_calls[0]["rounding_source_amount"], 1292.02)
        self.assertEqual(result["items"][0]["rounding_difference"], -0.02)

    def test_attachment_failure_is_warning_and_never_turns_payment_into_failure(self):
        fake = _FakeOdooIntegration()

        def _fail_attachment(*_args, **_kwargs):
            raise ValueError("sin permiso para adjuntar")

        fake.attach_totalnet_receipt_to_payment = _fail_attachment
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon, "mark_cupones_processed", lambda *_args: None
        ):
            result = asyncio.run(endpoints.confirm(self._request()))

        item = result["items"][0]
        self.assertTrue(item["ok"])
        self.assertFalse(item["attachment_ok"])
        self.assertIn("El pago se registro", item["warning"])

    def test_missing_payment_id_warns_without_attaching_to_the_wrong_record(self):
        fake = _FakeOdooIntegration(payment_id=None)
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon, "mark_cupones_processed", lambda *_args: None
        ):
            result = asyncio.run(endpoints.confirm(self._request()))

        item = result["items"][0]
        self.assertTrue(item["ok"])
        self.assertFalse(item["attachment_ok"])
        self.assertIn("no se pudo ubicar el pago creado", item["warning"])
        self.assertEqual(fake.attachment_calls, [])

    def test_confirm_rejects_unknown_operator_before_registering_any_payment(self):
        fake = _FakeOdooIntegration(operator_exists=False)
        with patch.object(endpoints, "odoo_integration", fake):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(endpoints.confirm(self._request(operator="unknown")))

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("no tiene credenciales Odoo", raised.exception.detail)
        self.assertEqual(fake.payment_calls, [])

    def test_history_is_flattened_and_links_to_invoice_and_payment(self):
        fake = _FakeOdooIntegration()
        state = {
            "processed_cupon_ids": [77],
            "history": [
                {
                    "at": "2026-10-08T14:30:00",
                    "payments": [
                        {
                            "ok": True,
                            "cupon_id": 77,
                            "invoice_id": 100,
                            "result": {
                                "invoice_id": 100,
                                "action_result": {
                                    "res_model": "account.payment",
                                    "res_id": 950,
                                },
                            },
                            "original_amount": 490.0,
                            "attachment": {
                                "filename": "TotalNet_Fact_30300_Ticket_815_Cupon_77.pdf"
                            },
                        }
                    ],
                }
            ],
        }
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon, "load_state", return_value=state
        ):
            result = asyncio.run(endpoints.get_history())

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["registered_at"], "2026-10-08T14:30:00")
        self.assertEqual(result["items"][0]["payment_id"], 950)
        self.assertEqual(result["items"][0]["invoice_name"], "Factura 30300")
        self.assertEqual(result["items"][0]["cupon"]["ticket"], "815")
        self.assertIn("model=account.move", result["items"][0]["invoice_url"])
        self.assertIn("model=account.payment", result["items"][0]["payment_url"])
        self.assertEqual(result["items"][0]["source"], "totalnet")

    def test_history_includes_mercadolibre_payments_without_fake_coupon(self):
        fake = _FakeOdooIntegration()
        state = {
            "processed_cupon_ids": [],
            "history": [
                {
                    "at": "2026-10-08T15:00:00",
                    "payments": [
                        {
                            "source": "mercadolibre",
                            "ok": True,
                            "invoice_id": 100,
                            "invoice_name": "e-Ticket A-31028",
                            "payment_id": 951,
                            "attachment": {
                                "filename": "MercadoLibre_Orden_2000015420705457_Pago_99887766.pdf"
                            },
                            "mercadolibre": {"reference": "2000015420705457", "amount": 1154.0},
                        }
                    ],
                }
            ],
        }
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon, "load_state", return_value=state
        ):
            result = asyncio.run(endpoints.get_history())

        item = result["items"][0]
        self.assertEqual(item["source"], "mercadolibre")
        self.assertNotIn("cupon", item)
        self.assertEqual(item["mercadolibre"]["reference"], "2000015420705457")
        self.assertIn("model=account.payment", item["payment_url"])

    def test_confirm_explains_how_to_fix_a_missing_journal(self):
        fake = _FakeOdooIntegration()
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon,
            "load_recon_config",
            lambda: {"journal_map": {}},
        ):
            result = asyncio.run(endpoints.confirm(self._request(journal_id=None)))

        self.assertFalse(result["items"][0]["ok"])
        self.assertIn("VISA", result["items"][0]["error"])
        self.assertIn("Selecciona un diario", result["items"][0]["error"])
        self.assertEqual(fake.payment_calls, [])

    def test_sync_queries_totalnet_by_extended_settlement_window_and_filters_by_sale_date(self):
        fake_odoo = _FakeOdooIntegration()
        captured_calls = []

        date_from = date_to = (date.today() - timedelta(days=30)).isoformat()
        outside_requested_range_date = (date.today() - timedelta(days=15)).isoformat()

        def fake_get_all_cupones(settlement_from, settlement_to):
            captured_calls.append((settlement_from, settlement_to))
            return [
                {
                    "transaccion": {
                        "cupon_id": 1,
                        "fecha_cupon": date_to,
                        "importe": 490,
                        "moneda": "UYU",
                        "sello": "VISA",
                    }
                },
                {
                    # Liquido dentro de la ventana ampliada pero la venta fue
                    # fuera del rango pedido: no debe contarse.
                    "transaccion": {
                        "cupon_id": 2,
                        "fecha_cupon": outside_requested_range_date,
                        "importe": 490,
                        "moneda": "UYU",
                        "sello": "VISA",
                    }
                },
            ]

        request = endpoints.PosReconciliationSyncRequest(date_from=date_from, date_to=date_to)

        with patch.object(endpoints, "odoo_integration", fake_odoo), patch.object(
            endpoints.totalnet_integration, "is_configured", return_value=True
        ), patch.object(
            endpoints.totalnet_integration, "get_all_cupones", side_effect=fake_get_all_cupones
        ), patch.object(
            endpoints.recon,
            "load_recon_config",
            return_value={"settlement_lookahead_days": 10, "journal_map": {}},
        ), patch.object(
            endpoints.recon, "load_processed_cupon_ids", return_value=set()
        ):
            result = asyncio.run(endpoints.sync(request))

        expected_settlement_to = (date.today() - timedelta(days=20)).isoformat()
        self.assertEqual(captured_calls[0], (date_from, expected_settlement_to))
        self.assertEqual(result["settlement_date_from"], date_from)
        self.assertEqual(result["settlement_date_to"], expected_settlement_to)
        self.assertEqual(result["total_cupones"], 1)

    def test_pending_invoices_are_loaded_from_odoo_without_totalnet(self):
        fake = _FakeOdooIntegration()
        request = endpoints.PosReconciliationSyncRequest(
            date_from="2026-08-17",
            date_to="2026-08-17",
        )
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.totalnet_integration,
            "get_all_cupones",
            side_effect=AssertionError("No debe consultar TotalNet"),
        ):
            result = asyncio.run(endpoints.pending_invoices(request))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["name"], "e-Factura A-49947")
        self.assertEqual(result["items"][0]["rounded_amount"], 1035.0)
        self.assertTrue(fake.invoice_search_calls[0]["only_pending"])
        self.assertTrue(fake.invoice_search_calls[0]["only_cash_payment_term"])

    def test_manual_ticket_finds_numbered_cash_invoice_without_totalnet(self):
        fake = _FakeOdooIntegration()
        request = endpoints.ManualPosTicketRequest(
            transaction_date="2026-08-17",
            invoice_number="49947",
            amount=1035.0,
            currency="UYU",
            ticket="0926",
            authorization="074234",
            brand="VISA",
            product="DEBITO",
            batch="393",
            terminal="30983093",
            last_four="6294",
        )
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon, "load_processed_cupon_ids", return_value=set()
        ), patch.object(
            endpoints.recon,
            "load_recon_config",
            return_value={"amount_tolerance": 0.01, "date_window_days": 2, "journal_map": {"VISA": 7}},
        ), patch.object(
            endpoints.totalnet_integration,
            "get_all_cupones",
            side_effect=AssertionError("No debe consultar TotalNet"),
        ):
            result = asyncio.run(endpoints.manual_match(request))

        self.assertEqual(result["source"], "manual_ticket")
        self.assertEqual(len(result["matches_unicos"]), 1)
        match = result["matches_unicos"][0]
        self.assertEqual(match["invoice"]["name"], "e-Factura A-49947")
        self.assertTrue(match["can_confirm"])
        self.assertTrue(match["requires_rounding_writeoff"])
        self.assertTrue(match["cupon"]["manual_entry"])
        self.assertTrue(str(match["cupon"]["cupon_id"]).startswith("manual-"))
        self.assertEqual(match["suggested_journal_id"], 7)
        self.assertEqual(match["suggested_memo"], "Ticket 0926 | Lote 393")

    def test_manual_ticket_cannot_be_prepared_twice_after_confirmation(self):
        fake = _FakeOdooIntegration()
        request = endpoints.ManualPosTicketRequest(
            transaction_date="2026-08-17",
            invoice_number="49947",
            amount=1035.0,
            ticket="0926",
            authorization="074234",
            brand="VISA",
        )
        fingerprint = (
            "2026-08-17|49947|1035.00|UYU|0926|074234|visa"
        )
        import hashlib

        coupon_id = "manual-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
        with patch.object(endpoints, "odoo_integration", fake), patch.object(
            endpoints.recon, "load_processed_cupon_ids", return_value={coupon_id}
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(endpoints.manual_match(request))

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake.invoice_search_calls, [])


if __name__ == "__main__":
    unittest.main()
