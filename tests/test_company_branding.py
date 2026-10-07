import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import company_branding
from account_statement_pdf import generate_statement_pdf
from totalnet_receipt_pdf import generate_totalnet_transaction_pdf


def _png(width=1600, height=400):
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
    pixmap.set_rect(pixmap.irect, (175, 52, 60))
    return pixmap.tobytes("png")


class _FakeOdoo:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def is_configured(self):
        return True

    def get_company_branding(self):
        self.calls += 1
        if self.fail:
            raise ValueError("Odoo caido")
        return {
            "name": "Aramid",
            "logo": base64.b64encode(_png()).decode(),
            "primary_color": "#af343c",
            "street": "Isla de Flores 1368",
            "city": "Montevideo",
            "phone": "2902 0202",
            "email": "contacto@aramid.com.uy",
            "website": "http://aramid.com.uy",
            "vat": "212388710019",
        }


class TestCompanyBranding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.patchers = [
            patch.object(company_branding, "_resolve_path", lambda name: self.dir / name),
            patch.dict(company_branding._memory, {"at": 0.0, "data": None}),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self):
        for item in self.patchers:
            item.stop()
        self.tmp.cleanup()

    def test_reads_odoo_and_shrinks_large_logo(self):
        branding = company_branding.get_branding(_FakeOdoo())
        self.assertEqual(branding["source"], "odoo")
        self.assertEqual(branding["accent"], "#af343c")
        self.assertEqual(branding["website"], "aramid.com.uy")
        self.assertEqual(branding["address"], "Isla de Flores 1368, Montevideo")
        self.assertEqual(fitz.Pixmap(branding["logo"]).width, company_branding.MAX_LOGO_WIDTH_PX)

    def test_memory_cache_avoids_repeated_odoo_calls(self):
        odoo = _FakeOdoo()
        company_branding.get_branding(odoo)
        company_branding.get_branding(odoo)
        self.assertEqual(odoo.calls, 1)

    def test_odoo_failure_uses_last_saved_copy(self):
        company_branding.get_branding(_FakeOdoo())
        company_branding._memory.update({"at": 0.0, "data": None})
        branding = company_branding.get_branding(_FakeOdoo(fail=True), force=True)
        self.assertEqual(branding["source"], "cache")
        self.assertTrue(branding["logo"])

    def test_without_odoo_or_cache_is_neutral_and_never_raises(self):
        branding = company_branding.get_branding(_FakeOdoo(fail=True))
        self.assertEqual(branding["source"], "neutral")
        self.assertEqual(branding["logo"], b"")

    def test_local_overrides_win(self):
        logo_path = self.dir / "otro.png"
        logo_path.write_bytes(_png(200, 50))
        (self.dir / "branding_config.json").write_text(
            json.dumps({"accent": "#123456", "logo_path": str(logo_path)}), encoding="utf-8"
        )
        branding = company_branding.get_branding(_FakeOdoo())
        self.assertEqual(branding["accent"], "#123456")
        self.assertEqual(fitz.Pixmap(branding["logo"]).width, 200)

    def test_invalid_color_falls_back(self):
        self.assertEqual(company_branding.hex_to_rgb("rojo"), company_branding.hex_to_rgb(company_branding.NEUTRAL_ACCENT))

    def test_pdfs_embed_logo_once_and_company_data(self):
        branding = company_branding.get_branding(_FakeOdoo())
        invoices = [
            {"name": f"A-{i}", "invoice_date": "2026-01-01", "due_date": "2026-02-01", "days_overdue": 200,
             "currency": "UYU", "amount_total": 10.0, "residual": 10.0}
            for i in range(90)
        ]
        client = {"name": "Cliente", "balance_by_currency": {"UYU": 900.0}, "overdue_by_currency": {"UYU": 900.0}}
        for pdf in (
            generate_statement_pdf(client, invoices, "Aramid", "2026-10-06", branding),
            generate_totalnet_transaction_pdf({"cupon_id": 1, "importe": 10}, branding),
        ):
            with fitz.open(stream=pdf, filetype="pdf") as document:
                images = {img[0] for page in document for img in page.get_images()}
                text = document[0].get_text()
            self.assertEqual(len(images), 1)
            self.assertIn("RUT 212388710019", text)
            self.assertIn("aramid.com.uy", text)

    def test_pdfs_still_render_without_branding(self):
        pdf = generate_statement_pdf({"name": "X"}, [], "Aramid", "2026-10-06")
        with fitz.open(stream=pdf, filetype="pdf") as document:
            self.assertIn("Aramid", document[0].get_text())


if __name__ == "__main__":
    unittest.main()
