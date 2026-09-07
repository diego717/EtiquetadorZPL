import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_HTML = PROJECT_ROOT / "web" / "config.html"


class TestPosReconciliationUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CONFIG_HTML.read_text(encoding="utf-8")

    def test_post_confirmation_refresh_preserves_journal_and_result_message(self):
        self.assertIn("await syncPosReconciliation({", self.source)
        self.assertIn("preservePaymentContext: true", self.source)
        self.assertIn("preserveConfirmSummary: true", self.source)
        self.assertIn("if (!preservePaymentContext)", self.source)
        self.assertIn("if (!preserveConfirmSummary)", self.source)

    def test_manual_sync_still_starts_a_fresh_reconciliation(self):
        self.assertIn('onclick="syncPosReconciliation()"', self.source)

    def test_pos_reconciliation_has_an_isolated_full_page_view(self):
        self.assertIn("get('view') === 'pos'", self.source)
        self.assertIn("body:not(.pos-only-view) #pos-reconciliation-section", self.source)
        self.assertIn('id="nav-pos-link"', self.source)

    def test_pending_odoo_invoices_do_not_depend_on_totalnet(self):
        self.assertIn('/api/pos-reconciliation/pending-invoices', self.source)
        self.assertIn('id="pos-pending-invoices-body"', self.source)
        self.assertIn('await loadPosPendingInvoices(dateFrom, dateTo);', self.source)

    def test_manual_ticket_form_uses_preview_before_confirmation(self):
        self.assertIn('id="pos-manual-panel"', self.source)
        self.assertIn('/api/pos-reconciliation/manual-match', self.source)
        self.assertIn('Buscar factura en Odoo', self.source)
        self.assertIn("posSyncResult = result;", self.source)


if __name__ == "__main__":
    unittest.main()
