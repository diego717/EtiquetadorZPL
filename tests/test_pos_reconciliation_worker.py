import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import pos_reconciliation as recon
import pos_reconciliation_worker as worker_module
from pos_reconciliation_worker import PosReconciliationWorker


def _match(
    cupon_id=1,
    invoice_number="49947",
    amount=1035.34,
    invoice_total=1035.34,
    residual=None,
    payment_state="not_paid",
    matched_by="numero_factura_totalnet",
    journal_id=3,
):
    residual = invoice_total if residual is None else residual
    amount_matches = round(invoice_total - amount, 2) == 0
    return {
        "cupon": {
            "cupon_id": cupon_id,
            "numero_factura": invoice_number,
            "importe": amount,
            "fecha": "2026-10-01",
            "sello": "VISA",
            "manual_entry": False,
        },
        "invoice": {
            "invoice_id": 100 + cupon_id,
            "name": f"e-Factura A-{invoice_number}",
            "amount_total": invoice_total,
            "amount_residual": residual,
            "payment_state": payment_state,
            "can_register_payment": payment_state in {"not_paid", "partial"},
        },
        "matched_by": matched_by,
        "amount_matches": amount_matches,
        "requires_rounding_writeoff": False,
        "currency_matches": True,
        "can_confirm": amount_matches and payment_state in {"not_paid", "partial"},
        "suggested_journal_id": journal_id,
        "suggested_memo": "memo",
    }


def _counts(*matches):
    counts = {}
    for match in matches:
        number = recon._invoice_number(match["cupon"]["numero_factura"])
        counts[number] = counts.get(number, 0) + 1
    return counts


class TestDeterministicRules(unittest.TestCase):
    def assertRejected(self, match, reason, counts=None):
        self.assertEqual(
            recon.deterministic_rejection_reason(match, counts or _counts(match)), reason
        )

    def test_exact_invoice_number_match_is_deterministic(self):
        match = _match()
        self.assertEqual(recon.deterministic_rejection_reason(match, _counts(match)), "")

    def test_amount_date_fallback_is_never_automatic(self):
        self.assertRejected(_match(matched_by="importe_fecha"), "no_coincide_por_numero_de_factura")

    def test_amount_difference_is_never_automatic(self):
        self.assertRejected(_match(amount=1035.0), "no_confirmable")

    def test_partially_paid_invoice_is_never_automatic(self):
        self.assertRejected(
            _match(payment_state="partial"),
            "factura_con_pagos_previos",
        )

    def test_missing_journal_mapping_is_never_automatic(self):
        self.assertRejected(_match(journal_id=None), "sin_diario_mapeado")

    def test_repeated_invoice_number_across_cupones_is_never_automatic(self):
        first = _match(cupon_id=1)
        second = _match(cupon_id=2)
        self.assertRejected(first, "numero_de_factura_repetido_en_cupones", _counts(first, second))

    def test_find_counts_numbers_in_unmatched_cupones_too(self):
        match = _match(cupon_id=1)
        proposal = {
            "matches_unicos": [match],
            "ambiguos": [],
            "sin_match": [{"cupon": {"cupon_id": 2, "numero_factura": "A-49947"}}],
        }
        self.assertEqual(recon.find_deterministic_matches(proposal), [])


class _FakeTotalNet:
    def is_configured(self):
        return True


class _FakeOdoo:
    def __init__(self):
        self.payments = []

    def is_configured(self):
        return True

    def resolve_operator_auth_exact(self, app_username):
        if app_username == "vale":
            return {"username": "vale@example.com", "password": "secret"}
        return None

    def register_invoice_payment(self, invoice_id, amount, payment_date, journal_id, memo, auth_override, *rest):
        self.payments.append({"invoice_id": invoice_id, "amount": amount, "journal_id": journal_id})
        return {"invoice_id": invoice_id, "payment_id": None, "payment_state": "in_payment"}


class _FakeNotifier:
    def __init__(self):
        self.messages = []

    def _send_notification(self, title, message, level="info"):
        self.messages.append((title, message))


class TestPosReconciliationWorker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self.config = dict(recon._default_recon_config())
        self.processed = []
        self.patches = [
            patch.object(recon, "_resolve_state_path", lambda name: tmp_path / name),
            patch.object(recon, "load_recon_config", lambda: dict(self.config)),
            patch.object(recon, "load_processed_cupon_ids", lambda: set()),
            patch.object(
                recon,
                "mark_cupones_processed",
                lambda ids, results: self.processed.append((list(ids), results)),
            ),
        ]
        for item in self.patches:
            item.start()
        self.odoo = _FakeOdoo()
        self.notifier = _FakeNotifier()
        self.worker = PosReconciliationWorker(totalnet=_FakeTotalNet(), odoo=self.odoo, notifier=self.notifier)
        self.proposal = {
            "matching_version": 4,
            "date_from": "2026-09-29",
            "date_to": "2026-10-05",
            "total_cupones": 3,
            "matches_unicos": [
                _match(cupon_id=1, invoice_number="100"),
                _match(cupon_id=2, invoice_number="200", amount=50.0),
                _match(cupon_id=4, invoice_number="400", payment_state="paid"),
            ],
            "ambiguos": [{"cupon": {"cupon_id": 3, "numero_factura": "300"}, "candidates": []}],
            "sin_match": [],
        }

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.tmp.cleanup()

    def _run(self):
        with patch.object(
            worker_module.service, "build_sync_proposal", lambda *args: self._fresh_proposal()
        ):
            return self.worker.run_cycle(force=True)

    def _fresh_proposal(self):
        import copy

        return copy.deepcopy(self.proposal)

    def test_disabled_worker_skips_without_force(self):
        result = self.worker.run_cycle()
        self.assertTrue(result["skipped"])
        self.assertEqual(self.odoo.payments, [])

    def test_cycle_prepares_proposal_and_notifies_without_registering(self):
        result = self._run()
        summary = result["summary"]
        self.assertEqual(summary["listos_para_revisar"], 1)
        self.assertEqual(summary["con_diferencia"], 1)
        self.assertEqual(summary["ya_pagadas"], 1)
        self.assertEqual(summary["ambiguos"], 1)
        self.assertEqual(summary["nuevos_para_revisar"], 2)
        self.assertEqual(self.odoo.payments, [])
        self.assertEqual(len(self.notifier.messages), 1)
        self.assertIsNotNone(self.worker.get_last_proposal())

    def test_same_pending_cupones_are_notified_only_once(self):
        self._run()
        result = self._run()
        self.assertEqual(result["summary"]["nuevos_para_revisar"], 0)
        self.assertEqual(len(self.notifier.messages), 1)

    def test_auto_register_only_registers_deterministic_matches(self):
        self.config.update({"auto_register_deterministic": True, "auto_register_operator": "vale"})
        result = self._run()
        self.assertEqual([p["invoice_id"] for p in self.odoo.payments], [101])
        self.assertEqual(result["summary"]["registrados_automaticamente"], 1)
        self.assertEqual(result["summary"]["listos_para_revisar"], 0)
        self.assertEqual(self.processed[0][0], [1])
        self.assertEqual(self.processed[0][1][0]["mode"], "automatico_deterministico")
        remaining = [m["cupon"]["cupon_id"] for m in self.worker.state["last_proposal"]["matches_unicos"]]
        self.assertEqual(remaining, [2, 4])

    def test_auto_register_without_valid_operator_registers_nothing(self):
        self.config.update({"auto_register_deterministic": True, "auto_register_operator": "nadie"})
        self._run()
        self.assertEqual(self.odoo.payments, [])
        self.assertTrue(any("credenciales" in e["message"] for e in self.worker.state["recent_events"]))

    def test_errors_are_recorded_and_do_not_raise(self):
        with patch.object(worker_module.service, "build_sync_proposal", side_effect=ValueError("TotalNet 500")):
            result = self.worker.run_cycle(force=True)
        self.assertFalse(result["ok"])
        self.assertEqual(self.worker.get_status()["last_error"], "TotalNet 500")


if __name__ == "__main__":
    unittest.main()
