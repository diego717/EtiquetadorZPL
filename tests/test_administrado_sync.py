import sys
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from administrado_integration import AdministradoIntegration


class TestAdministradoSync(unittest.TestCase):
    def test_list_label_links_prefers_requests_before_playwright(self):
        integration = AdministradoIntegration()
        integration.config["cookie_header"] = "test-cookie"
        integration.config["use_playwright"] = True

        expected = [{"envio_id": "123", "print_mode": "imprimir"}]
        integration._list_label_links_via_requests = lambda limit=20: (expected, True)
        integration.list_label_links_playwright = lambda limit=20: self.fail("No deberia usar Playwright")

        result = integration.list_label_links(limit=20)

        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
