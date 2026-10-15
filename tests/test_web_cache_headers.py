import os
import sys
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))
sys.path.insert(0, str(project_root / "config"))


class TestWebCacheHeaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # El montaje de /web usa una ruta relativa al directorio del proyecto.
        cls._cwd = os.getcwd()
        os.chdir(project_root)
        from fastapi.testclient import TestClient
        import fastapi_real

        # Sin "with": no corre el startup (no arranca workers ni impresion).
        cls.client = TestClient(fastapi_real.app)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)

    def test_web_files_are_revalidated_and_unchanged_files_return_304(self):
        first = self.client.get("/web/mercadolibre.js")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers.get("cache-control"), "no-cache")
        etag = first.headers.get("etag")
        self.assertTrue(etag)

        again = self.client.get("/web/mercadolibre.js", headers={"If-None-Match": etag})
        self.assertEqual(again.status_code, 304)

    def test_html_pages_are_revalidated_too(self):
        response = self.client.get("/web/config.html")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-cache")

    def test_api_responses_are_not_touched(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("cache-control", response.headers)


if __name__ == "__main__":
    unittest.main()
