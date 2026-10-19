import io
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from PIL import Image

import trabajos_print
from trabajos_print import format_due_date, order_label_html, validate_images, work_order_html


def _png(width=703, height=224):
    out = io.BytesIO()
    Image.new("L", (width, height), 255).save(out, "PNG")
    return out.getvalue()


JOB = {"row": 4, "order": "S58794", "customer": "Polakof <Y> Cia", "product": "CARTEL", "quantity": "1",
       "due": "13-oct", "due_date": "2026-10-13", "priority": "", "finished": ""}


class TestFormatDueDate(unittest.TestCase):
    def test_uses_full_date_when_available(self):
        self.assertEqual(format_due_date("2026-10-13", "13-oct"), "Martes 13 Octubre")

    def test_parses_sheet_text_with_current_year(self):
        self.assertEqual(format_due_date("", "4-sept", today=date(2026, 1, 1)), "Viernes 4 Septiembre")

    def test_empty_is_stock(self):
        self.assertEqual(format_due_date("", ""), "-- STOCK --")

    def test_unknown_text_is_kept_escaped(self):
        self.assertEqual(format_due_date("", "a <confirmar>"), "a &lt;confirmar&gt;")


class TestHtml(unittest.TestCase):
    def test_order_label_escapes_sheet_text(self):
        content = order_label_html(JOB)
        self.assertIn("Polakof &lt;Y&gt; Cia", content)
        self.assertIn("size: 88mm 28mm", content)

    def test_work_order_priority_colors(self):
        self.assertIn("#f1c232", work_order_html([dict(JOB, priority="2º PRIORIDAD")]))
        self.assertIn("#cc0000", work_order_html([dict(JOB, priority="1º PRIORIDAD")]))
        self.assertNotIn("#cc0000", work_order_html([JOB]))

    def test_work_order_optional_blocks(self):
        plain = work_order_html([JOB])
        self.assertNotIn('class="caja-notas"', plain)
        self.assertNotIn('class="img-box"', plain)
        full = work_order_html([dict(JOB, finished="Doble faz")], "50", "Ojo", ["data:image/png;base64,AAAA"])
        self.assertIn('class="caja-notas">Doble faz', full)
        self.assertIn('<img src="data:image/png;base64,AAAA"', full)
        self.assertIn('class="texto-extra">Ojo', full)
        self.assertIn(">50<", full)


class TestValidateImages(unittest.TestCase):
    def test_accepts_data_urls(self):
        self.assertEqual(validate_images(["data:image/jpeg;base64,/9j/AA=="]), ["data:image/jpeg;base64,/9j/AA=="])

    def test_rejects_external_urls(self):
        with self.assertRaises(ValueError):
            validate_images(["https://example.com/x.png"])

    def test_rejects_too_many(self):
        with self.assertRaises(ValueError):
            validate_images(["data:image/png;base64,AA=="] * (trabajos_print.MAX_IMAGES + 1))


class TestPrintOrderLabels(unittest.TestCase):
    def test_sends_one_zpl_per_label_and_copy(self):
        sent = []
        fake_printer = types.SimpleNamespace(send_raw_to_printer=lambda data, printer, job_name="": sent.append((data, printer)) or True)
        with patch.object(trabajos_print, "render_labels_png", return_value=[_png(), _png()]), \
                patch.object(trabajos_print, "label_printer", return_value="Godex GE300"), \
                patch.dict(sys.modules, {"printer": fake_printer}):
            result = trabajos_print.print_order_labels([JOB, JOB], copies=2)

        self.assertEqual(result, {"success": True, "printer": "Godex GE300", "labels": 4})
        self.assertEqual(len(sent), 1)
        data, printer = sent[0]
        self.assertEqual(printer, "Godex GE300")
        self.assertEqual(data.count(b"^XA"), 4)
        self.assertIn(b"^PW704", data)
        self.assertIn(b"^LL224", data)

    def test_preview_does_not_print(self):
        with patch.object(trabajos_print, "render_labels_png", return_value=[_png(), _png()]), \
                patch.object(trabajos_print, "label_printer", side_effect=AssertionError("no deberia imprimir")):
            result = trabajos_print.print_order_labels([JOB, JOB], preview=True)

        self.assertEqual(result["content_type"], "image/png")
        with Image.open(io.BytesIO(result["preview"])) as img:
            self.assertEqual(img.size, (703, 224 * 2 + 12))


if __name__ == "__main__":
    unittest.main()
