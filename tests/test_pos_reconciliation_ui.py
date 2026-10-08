import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_HTML = PROJECT_ROOT / "web" / "config.html"
CONFIG_CSS = PROJECT_ROOT / "web" / "config.css"
CONFIG_UI_JS = PROJECT_ROOT / "web" / "config-ui.js"
SYSTEM_CONFIG_JS = PROJECT_ROOT / "web" / "system-config.js"
CONFIG_PAGE_JS = PROJECT_ROOT / "web" / "config-page.js"
ADMINISTRADO_JS = PROJECT_ROOT / "web" / "administrado.js"
DISPATCH_PANEL_JS = PROJECT_ROOT / "web" / "dispatch-panel.js"
ODOO_CONFIG_JS = PROJECT_ROOT / "web" / "odoo-config.js"
MERCADOLIBRE_JS = PROJECT_ROOT / "web" / "mercadolibre.js"
POS_RECONCILIATION_JS = PROJECT_ROOT / "web" / "pos-reconciliation.js"


class TestPosReconciliationUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CONFIG_HTML.read_text(encoding="utf-8")
        cls.styles = CONFIG_CSS.read_text(encoding="utf-8")
        cls.ui_script = CONFIG_UI_JS.read_text(encoding="utf-8")
        cls.system_config_script = SYSTEM_CONFIG_JS.read_text(encoding="utf-8")
        cls.page_script = CONFIG_PAGE_JS.read_text(encoding="utf-8")
        cls.administrado_script = ADMINISTRADO_JS.read_text(encoding="utf-8")
        cls.dispatch_script = DISPATCH_PANEL_JS.read_text(encoding="utf-8")
        cls.odoo_script = ODOO_CONFIG_JS.read_text(encoding="utf-8")
        cls.mercadolibre_script = MERCADOLIBRE_JS.read_text(encoding="utf-8")
        cls.script = POS_RECONCILIATION_JS.read_text(encoding="utf-8")

    def test_config_styles_are_loaded_from_a_separate_stylesheet(self):
        self.assertIn('<link rel="stylesheet" href="config.css">', self.source)
        self.assertNotIn("<style>", self.source)
        self.assertIn(".pos-history-filters", self.styles)

    def test_shared_ui_is_loaded_from_a_separate_script(self):
        self.assertIn('<script src="config-ui.js"></script>', self.source)
        self.assertNotIn("function uiConfirm(opts = {})", self.source)
        self.assertIn("function uiConfirm(opts = {})", self.ui_script)
        self.assertIn("function initTheme()", self.ui_script)
        self.assertIn("function initViewMode()", self.ui_script)

    def test_system_config_is_loaded_from_a_separate_script(self):
        self.assertIn('<script src="system-config.js"></script>', self.source)
        self.assertNotIn("async function saveNotificationConfig()", self.source)
        self.assertIn("async function saveNotificationConfig()", self.system_config_script)
        self.assertIn("async function saveBackupConfig()", self.system_config_script)
        self.assertIn("async function restoreBackup", self.system_config_script)
        self.assertIn("async function clearDatabase()", self.system_config_script)

    def test_page_controller_is_loaded_without_inline_javascript(self):
        self.assertIn('<script src="config-page.js"></script>', self.source)
        self.assertNotIn("<script>", self.source)
        self.assertNotIn("async function fetchAPI(endpoint)", self.source)
        self.assertIn("async function fetchAPI(endpoint)", self.page_script)
        self.assertIn("function renderHealthBar()", self.page_script)
        self.assertIn("const DIRTY_SCOPES", self.page_script)
        self.assertIn("window.addEventListener('beforeunload'", self.page_script)

    def test_pos_logic_is_loaded_from_a_separate_script(self):
        self.assertIn('<script src="pos-reconciliation.js"></script>', self.source)
        self.assertNotIn("function renderPosResults()", self.source)
        self.assertIn("function renderPosResults()", self.script)

    def test_administrado_logic_is_loaded_from_a_separate_script(self):
        self.assertIn('<script src="administrado.js"></script>', self.source)
        self.assertNotIn("function renderAdministradoSales()", self.source)
        self.assertIn("function renderAdministradoSales()", self.administrado_script)
        self.assertIn("async function printAdministradoShipment", self.administrado_script)

    def test_dispatch_panel_is_loaded_from_a_separate_script(self):
        self.assertIn('<script src="dispatch-panel.js"></script>', self.source)
        self.assertNotIn("function renderDispatchTasks()", self.source)
        self.assertIn("function renderDispatchTasks()", self.dispatch_script)
        self.assertIn("async function retryFailedVisibleDispatchTasks", self.dispatch_script)

    def test_odoo_config_is_loaded_from_a_separate_script(self):
        self.assertIn('<script src="odoo-config.js"></script>', self.source)
        self.assertNotIn("function updateOdooForm()", self.source)
        self.assertIn("function updateOdooForm()", self.odoo_script)
        self.assertIn("async function loadOdooPrinters", self.odoo_script)
        self.assertIn("async function saveOdooOperatorUser", self.odoo_script)

    def test_mercadolibre_is_loaded_from_a_separate_script(self):
        self.assertIn('<script src="mercadolibre.js"></script>', self.source)
        self.assertNotIn("function updateMercadoLibreForm()", self.source)
        self.assertIn("function updateMercadoLibreForm()", self.mercadolibre_script)
        self.assertIn("async function startMercadoLibreOAuth", self.mercadolibre_script)
        self.assertIn("async function syncMercadoLibreSales", self.mercadolibre_script)

    def test_post_confirmation_refresh_preserves_journal_and_result_message(self):
        self.assertIn("await syncPosReconciliation({", self.script)
        self.assertIn("preservePaymentContext: true", self.script)
        self.assertIn("preserveConfirmSummary: true", self.script)
        self.assertIn("if (!preservePaymentContext)", self.script)
        self.assertIn("if (!preserveConfirmSummary)", self.script)

    def test_manual_sync_still_starts_a_fresh_reconciliation(self):
        self.assertIn('onclick="syncPosReconciliation()"', self.source)

    def test_pos_reconciliation_has_an_isolated_full_page_view(self):
        self.assertIn("get('view') === 'pos'", self.ui_script)
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
