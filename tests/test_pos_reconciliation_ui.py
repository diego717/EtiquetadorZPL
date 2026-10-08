import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_HTML = PROJECT_ROOT / "web" / "config.html"
CONFIG_CSS = PROJECT_ROOT / "web" / "config.css"
POS_RECONCILIATION_JS = PROJECT_ROOT / "web" / "pos-reconciliation.js"


class TestPosReconciliationUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CONFIG_HTML.read_text(encoding="utf-8")
        cls.styles = CONFIG_CSS.read_text(encoding="utf-8")
        cls.script = POS_RECONCILIATION_JS.read_text(encoding="utf-8")

    def test_config_styles_are_loaded_from_a_separate_stylesheet(self):
        self.assertIn('<link rel="stylesheet" href="config.css">', self.source)
        self.assertNotIn("<style>", self.source)
        self.assertIn(".pos-history-filters", self.styles)

    def test_pos_logic_is_loaded_from_a_separate_script(self):
        self.assertIn('<script src="pos-reconciliation.js"></script>', self.source)
        self.assertNotIn("function renderPosResults()", self.source)
        self.assertIn("function renderPosResults()", self.script)

    def test_post_confirmation_refresh_preserves_journal_and_result_message(self):
        self.assertIn("await syncPosReconciliation({", self.script)
        self.assertIn("preservePaymentContext: true", self.script)
        self.assertIn("preserveConfirmSummary: true", self.script)
        self.assertIn("if (!preservePaymentContext)", self.script)
        self.assertIn("if (!preserveConfirmSummary)", self.script)

    def test_manual_sync_still_starts_a_fresh_reconciliation(self):
        self.assertIn('onclick="syncPosReconciliation()"', self.source)

    def test_pos_reconciliation_has_an_isolated_full_page_view(self):
        self.assertIn("get('view') === 'pos'", self.source)
        self.assertIn("body:not(.pos-only-view) #pos-reconciliation-section", self.styles)
        self.assertIn('id="nav-pos-link"', self.source)

    def test_pending_odoo_invoices_do_not_depend_on_totalnet(self):
        self.assertIn('/api/pos-reconciliation/pending-invoices', self.script)
        self.assertIn('id="pos-pending-invoices-body"', self.source)
        self.assertIn('await loadPosPendingInvoices(dateFrom, dateTo);', self.script)

    def test_manual_ticket_form_uses_preview_before_confirmation(self):
        self.assertIn('id="pos-manual-panel"', self.source)
        self.assertIn('/api/pos-reconciliation/manual-match', self.script)
        self.assertIn('Buscar factura en Odoo', self.source)
        self.assertIn("posSyncResult = result;", self.script)


if __name__ == "__main__":
    unittest.main()
