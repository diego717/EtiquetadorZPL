import asyncio
import base64
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))

import pos_reconciliation as recon  # noqa: E402
import pos_reconciliation_endpoints as endpoints  # noqa: E402
import pos_reconciliation_service as service  # noqa: E402

TODAY = date.today().isoformat()


class _FakeOdoo:
    def __init__(self, **context):
        self.context = {
            "invoice_id": 114296,
            "invoice_name": "e-Factura A-50915",
            "partner": "TEC ASOCIADOS S.R.L.",
            "move_type": "out_invoice",
            "state": "posted",
            "payment_state": "not_paid",
            "amount_residual": 256.20,
            "invoice_currency": "USD",
            "journal_id": 88,
            "journal_name": "BROU M/E",
            "journal_type": "bank",
            "journal_currency": "USD",
        }
        self.context.update(context)
        self.payments = []
        self.attachments = []

    def get_invoice_payment_context(self, invoice_id, journal_id, auth_override=None):
        return dict(self.context)

    def register_invoice_payment(self, *args):
        self.payments.append(args)
        return {"invoice_id": args[0], "payment_id": 951, "payment_state": "paid"}

    def attach_pdf_to_payment(self, payment_id, filename, content, auth_override=None, mimetype="application/pdf"):
        self.attachments.append((payment_id, filename, content, mimetype))
        return {"attachment_id": 7, "filename": filename}

    # Para el endpoint.
    def resolve_operator_auth_exact(self, username):
        return {"username": "vale@example.com", "password": "secret"} if username == "vale" else None

    def _authenticate(self, auth_override=None):
        return 1

    def record_url(self, model, record_id):
        return f"https://odoo.test/{model}/{record_id}"


class _StateIsolation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self.patcher = patch.object(recon, "_resolve_state_path", lambda name: tmp_path / name)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()


class TestRegisterTransferPayment(_StateIsolation):
    def _register(self, odoo, amount=256.20, **kwargs):
        params = {
            "invoice_id": 114296,
            "journal_id": 88,
            "amount": amount,
            "payment_date": TODAY,
            "reference": "OP-123 456",
            "auth_override": {"username": "u"},
        }
        params.update(kwargs)
        return service.register_transfer_payment(odoo, **params)

    def test_full_payment_registers_with_memo_and_no_writeoff(self):
        odoo = _FakeOdoo()
        entry = self._register(odoo)
        invoice_id, amount, payment_date, journal_id, memo, _auth, exact, writeoff, _src, label = odoo.payments[0]
        self.assertEqual((invoice_id, amount, payment_date, journal_id), (114296, 256.2, TODAY, 88))
        self.assertEqual(memo, "Transferencia OP-123 456 - e-Factura A-50915")
        self.assertFalse(exact)
        self.assertIsNone(writeoff)
        self.assertEqual(entry["source"], "transferencia")
        self.assertEqual(entry["payment_id"], 951)
        self.assertEqual(entry["transfer"]["journal_name"], "BROU M/E")
        self.assertEqual(entry["transfer"]["difference"], 0.0)

    def test_currency_mismatch_is_rejected_before_writing(self):
        odoo = _FakeOdoo(journal_currency="UYU", journal_name="Santander M/N")
        with self.assertRaises(ValueError) as caught:
            self._register(odoo)
        self.assertIn("USD", str(caught.exception))
        self.assertEqual(odoo.payments, [])

    def test_paid_invoice_and_non_bank_journal_are_rejected(self):
        with self.assertRaises(ValueError):
            self._register(_FakeOdoo(payment_state="paid"))
        with self.assertRaises(ValueError):
            self._register(_FakeOdoo(journal_type="cash"))
        with self.assertRaises(ValueError):
            self._register(_FakeOdoo(move_type="out_refund"))

    def test_partial_payment_keeps_balance_open(self):
        odoo = _FakeOdoo()
        entry = self._register(odoo, amount=200)
        self.assertIsNone(odoo.payments[0][7])
        self.assertEqual(entry["transfer"]["difference"], 56.2)
        self.assertEqual(entry["transfer"]["difference_handling"], "open")

    def test_bank_fee_can_close_invoice_against_account(self):
        odoo = _FakeOdoo()
        entry = self._register(odoo, amount=253.20, difference_handling="reconcile", difference_account_id=530102)
        self.assertEqual(odoo.payments[0][7], 530102)
        self.assertEqual(odoo.payments[0][9], "Diferencia cobro por transferencia")
        self.assertEqual(entry["transfer"]["difference_handling"], "reconcile")

    def test_cent_difference_is_labelled_as_rounding(self):
        odoo = _FakeOdoo()
        self._register(odoo, amount=256.00, difference_handling="reconcile", difference_account_id=550101)
        self.assertEqual(odoo.payments[0][7], 550101)
        self.assertEqual(odoo.payments[0][9], "Redondeo cobro por transferencia")

    def test_large_difference_cannot_close_invoice(self):
        odoo = _FakeOdoo()
        with self.assertRaises(ValueError) as caught:
            self._register(odoo, amount=200, difference_handling="reconcile", difference_account_id=530102)
        self.assertIn("pago parcial", str(caught.exception))
        self.assertEqual(odoo.payments, [])
        with self.assertRaises(ValueError):
            self._register(odoo, amount=253.20, difference_handling="reconcile")

    def test_reference_already_used_in_same_bank_is_rejected(self):
        recon.record_external_payments([self._register(_FakeOdoo())])
        odoo = _FakeOdoo()
        with self.assertRaises(ValueError) as caught:
            self._register(odoo, reference="op123456")
        self.assertIn("ya se registro", str(caught.exception))
        self.assertEqual(odoo.payments, [])
        # Otro banco: es otra transferencia.
        self._register(odoo, reference="op123456", journal_id=99)
        self.assertEqual(len(odoo.payments), 1)

    def test_invalid_inputs(self):
        odoo = _FakeOdoo()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        for kwargs in ({"reference": " "}, {"amount": 0}, {"payment_date": tomorrow}, {"difference_handling": "x"}):
            with self.assertRaises(ValueError, msg=kwargs):
                self._register(odoo, **kwargs)
        self.assertEqual(odoo.payments, [])

    def test_attachment_is_added_to_payment_with_its_type(self):
        odoo = _FakeOdoo()
        entry = self._register(odoo, attachment={"mimetype": "image/png", "content": b"png"})
        self.assertTrue(entry["attachment_ok"])
        payment_id, filename, content, mimetype = odoo.attachments[0]
        self.assertEqual((payment_id, content, mimetype), (951, b"png", "image/png"))
        self.assertEqual(filename, "Transferencia_OP123456_e-Factura_A-50915.png")


class TestTransferEndpoint(_StateIsolation):
    def _request(self, **overrides):
        values = {
            "operator_app_username": "VALE",
            "invoice_id": 114296,
            "journal_id": 88,
            "amount": 256.20,
            "payment_date": TODAY,
            "reference": "OP-1",
        }
        values.update(overrides)
        return endpoints.TransferPaymentRequest(**values)

    def test_registers_and_saves_history_with_links(self):
        odoo = _FakeOdoo()
        pdf = base64.b64encode(b"%PDF-1.4").decode()
        with patch.object(endpoints, "odoo_integration", odoo):
            result = asyncio.run(endpoints.register_transfer(
                self._request(attachment_base64=pdf, attachment_mimetype="application/pdf", attachment_filename="c.pdf")
            ))
        self.assertEqual(result["actor_odoo_username"], "vale@example.com")
        self.assertEqual(result["payment_url"], "https://odoo.test/account.payment/951")
        self.assertTrue(result["attachment_ok"])
        history = recon.load_state()["history"]
        self.assertEqual(history[-1]["payments"][0]["transfer"]["reference"], "OP-1")

        with patch.object(endpoints, "odoo_integration", odoo):
            listed = asyncio.run(endpoints.get_history())
        self.assertEqual(listed["items"][0]["source"], "transferencia")
        self.assertEqual(listed["items"][0]["payment_url"], "https://odoo.test/account.payment/951")

    def test_rejects_unknown_operator_and_bad_attachment(self):
        odoo = _FakeOdoo()
        with patch.object(endpoints, "odoo_integration", odoo):
            with self.assertRaises(endpoints.HTTPException):
                asyncio.run(endpoints.register_transfer(self._request(operator_app_username="nadie")))
            with self.assertRaises(endpoints.HTTPException) as caught:
                asyncio.run(endpoints.register_transfer(
                    self._request(attachment_base64="aGVsbG8=", attachment_mimetype="text/plain")
                ))
        self.assertIn("PDF", caught.exception.detail)
        self.assertEqual(odoo.payments, [])
        self.assertEqual(recon.load_state()["history"], [])


if __name__ == "__main__":
    unittest.main()
