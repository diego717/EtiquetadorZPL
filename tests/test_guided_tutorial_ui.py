import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_HTML = PROJECT_ROOT / "web" / "config.html"
CONFIG_CSS = PROJECT_ROOT / "web" / "config.css"
TOUR_ENGINE_JS = PROJECT_ROOT / "web" / "guided-tutorial.js"
POS_TUTORIAL_JS = PROJECT_ROOT / "web" / "pos-tutorial.js"


class TestGuidedTutorialUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = CONFIG_HTML.read_text(encoding="utf-8")
        cls.css = CONFIG_CSS.read_text(encoding="utf-8")
        cls.engine = TOUR_ENGINE_JS.read_text(encoding="utf-8")
        cls.tutorial = POS_TUTORIAL_JS.read_text(encoding="utf-8")

    def test_help_button_and_scripts_are_present(self):
        self.assertIn('id="tutorial-btn"', self.html)
        self.assertIn('onclick="openAppTutorial()"', self.html)
        self.assertIn('<script src="guided-tutorial.js"></script>', self.html)
        self.assertIn('<script src="pos-tutorial.js"></script>', self.html)
        self.assertIn('<script src="administrado-tutorial.js"></script>', self.html)
        self.assertIn("window.openPosTutorial", self.tutorial)

    def test_help_button_is_limited_to_pos_view(self):
        self.assertIn(".tutorial-launch-btn {", self.css)
        self.assertIn("body.pos-only-view .tutorial-launch-btn", self.css)

    def test_all_pos_tutorial_topics_are_available(self):
        for topic_id in (
            "totalnet",
            "automatic",
            "manual-ticket",
            "manual-payment",
            "mercadolibre",
            "history",
        ):
            self.assertIn(f"id: '{topic_id}'", self.tutorial)

    def test_administrado_tutorial_topics_and_targets_are_available(self):
        admin_tutorial = (PROJECT_ROOT / "web" / "administrado-tutorial.js").read_text(encoding="utf-8")
        for topic_id in ("daily", "print", "filters", "delivery", "setup"):
            self.assertIn(f"id: '{topic_id}'", admin_tutorial)
        for target in (
            "adm-sync-toolbar",
            "adm-filter-tabs",
            "adm-sales-table",
            "adm-tools",
            "adm-advanced-panel",
            "adm-sales-url",
            "adm-cookie-header",
        ):
            self.assertIn(f'id="{target}"', self.html)
        self.assertIn("window.openAdministradoTutorial", admin_tutorial)
        self.assertNotIn("setAdministradoFilter", admin_tutorial)
        self.assertIn("function firstSaleActions()", admin_tutorial)
        self.assertIn("function firstSalePrintButton()", admin_tutorial)

    def test_every_declared_id_target_exists(self):
        targets = set()
        marker = "target: '#"
        offset = 0
        while True:
            start = self.tutorial.find(marker, offset)
            if start < 0:
                break
            start += len(marker)
            end = start
            while end < len(self.tutorial) and self.tutorial[end] not in " .'\"":
                end += 1
            targets.add(self.tutorial[start:end])
            offset = end

        self.assertGreater(len(targets), 10)
        missing = [target for target in sorted(targets) if f'id="{target}"' not in self.html]
        self.assertEqual([], missing)

    def test_tutorial_supports_keyboard_and_restores_view(self):
        self.assertIn("event.key === 'Escape'", self.engine)
        self.assertIn("event.key === 'ArrowRight'", self.engine)
        self.assertIn("event.key === 'ArrowLeft'", self.engine)
        self.assertIn("restoreView", self.tutorial)
        self.assertIn("setPaymentSource(source, false)", self.tutorial)

    def test_tutorial_does_not_call_payment_actions(self):
        for action in (
            "syncPosReconciliation(",
            "confirmPosReconciliation(",
            "registerTransferPayment(",
            "registerMercadoLibrePayment(",
            "saveTotalNetConfig(",
            "renderPosResults(",
            "loadPosPendingInvoices(",
            "loadPosHistory(",
        ):
            self.assertNotIn(action, self.tutorial)


if __name__ == "__main__":
    unittest.main()
