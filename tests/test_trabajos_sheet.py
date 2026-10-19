import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

import trabajos_sheet
from trabajos_sheet import TrabajosSheet, parse_rows


def _row(row, values, link=""):
    return {"row": row, "values": values, "link": link, "stateColor": "#ffffff"}


SALE_VALUES = ["Marcelo", "S57619", "S57619", "DEVOTO HNOS S.A.", "SELLO 4910", "2", "21-ago", "28-ago",
               "Empezar", "", "TRUE", "-52", "FALSE", "2º PRIORIDAD", "8", "", "0", "", "62935", "", "VENTA"]
MFG_VALUES = ["Valentina", "962", "962", "", "TARJETA PVC", "50", "17-ago", "", "Procesando", "", "FALSE",
              "", "TRUE", "", "8", "", "4", "1005", "", "", "FABRICACION"]


class TestParseRows(unittest.TestCase):
    def test_maps_sheet_columns(self):
        sale_link = "https://odoo/web#id=62935&model=sale.order"
        items = parse_rows({"rows": [_row(4, SALE_VALUES, sale_link)]})

        self.assertEqual(items[0]["order"], "S57619")
        self.assertEqual(items[0]["kind"], "venta")
        self.assertEqual(items[0]["customer"], "DEVOTO HNOS S.A.")
        self.assertEqual(items[0]["state"], "Empezar")
        self.assertEqual(items[0]["days_left"], -52)
        self.assertTrue(items[0]["first"])
        self.assertFalse(items[0]["supplier"])
        self.assertEqual(items[0]["priority"], "2º PRIORIDAD")
        self.assertEqual(items[0]["link"], sale_link)

    def test_manufacturing_without_link_points_to_production(self):
        with patch.object(trabajos_sheet, "_manufacturing_url", side_effect=lambda rid: f"mrp/{rid}"):
            items = parse_rows({"rows": [_row(8, MFG_VALUES)]})

        self.assertEqual(items[0]["kind"], "fabricacion")
        self.assertIsNone(items[0]["days_left"])
        self.assertTrue(items[0]["supplier"])
        self.assertEqual(items[0]["link"], "mrp/1005")

    def test_short_rows_do_not_fail(self):
        items = parse_rows({"rows": [_row(9, ["", "970"])]})
        self.assertEqual(items[0]["order"], "970")
        self.assertEqual(items[0]["kind"], "")


class TestCache(unittest.TestCase):
    def test_keeps_last_data_when_sheet_fails(self):
        sheet = TrabajosSheet()
        sheet._fetch = lambda: {"items": [{"order": "S1"}], "generated_at": "x"}
        sheet.get()

        def fail():
            raise RuntimeError("sin conexion")

        sheet._fetch = fail
        result = sheet.get(force=True)

        self.assertEqual(result["items"], [{"order": "S1"}])
        self.assertEqual(result["error"], "sin conexion")

    def test_first_failure_raises(self):
        sheet = TrabajosSheet()
        sheet._fetch = lambda: (_ for _ in ()).throw(RuntimeError("sin config"))
        with self.assertRaises(RuntimeError):
            sheet.get()


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class TestSetState(unittest.TestCase):
    def setUp(self):
        self.sheet = TrabajosSheet()
        self.sheet._load_config = lambda: {"url": "https://script/exec", "token": "t"}
        self.sheet._cache = {"items": [], "error": ""}
        self.logged = []

    def test_posts_to_sheet_and_invalidates_cache(self):
        reply = {"ok": True, "row": 7, "state": "Finalizado", "previousState": "Procesando", "changed": True}
        with patch.object(trabajos_sheet.requests, "post", return_value=_FakeResponse(reply)) as post, \
                patch.object(trabajos_sheet, "_append_state_log", side_effect=self.logged.append):
            result = self.sheet.set_state(7, "S57686", "SELLO", "Finalizado", "diego")

        body = post.call_args.kwargs["json"]
        self.assertEqual(body["action"], "setState")
        self.assertEqual(body["token"], "t")
        self.assertEqual((body["row"], body["order"], body["state"], body["user"]), (7, "S57686", "Finalizado", "diego"))
        self.assertEqual(result["previousState"], "Procesando")
        self.assertIsNone(self.sheet._cache)
        self.assertEqual(self.logged[0]["from"], "Procesando")
        self.assertEqual(self.logged[0]["user"], "diego")

    def test_sheet_error_is_raised_and_not_logged(self):
        reply = {"ok": False, "error": "No se encontro la orden S1"}
        with patch.object(trabajos_sheet.requests, "post", return_value=_FakeResponse(reply)), \
                patch.object(trabajos_sheet, "_append_state_log", side_effect=self.logged.append):
            with self.assertRaisesRegex(RuntimeError, "No se encontro"):
                self.sheet.set_state(7, "S1", "", "Finalizado", "diego")

        self.assertEqual(self.logged, [])
        self.assertIsNotNone(self.sheet._cache)


class TestSheetConfigs(unittest.TestCase):
    def setUp(self):
        import json
        import tempfile

        self._json = json
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "trabajos_api.json"
        self.patcher = patch.object(trabajos_sheet, "_config_candidates", return_value=[self.path])
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.dir.cleanup()

    def write(self, data):
        self.path.write_text(self._json.dumps(data), encoding="utf-8")

    def test_single_sheet_format_is_principal(self):
        self.write({"url": "https://a/exec", "token": "t"})
        configs = trabajos_sheet.load_sheet_configs()
        self.assertEqual([(c["id"], c["url"]) for c in configs], [("principal", "https://a/exec")])
        self.assertEqual(configs[0]["printers"], {"label": "", "order": ""})

    def test_several_sheets_with_printers(self):
        self.write({"sheets": [
            {"id": "principal", "name": "Produccion", "url": "https://a/exec", "token": "t1"},
            {"id": "Otra Planilla", "name": "Otra", "url": "https://b/exec", "token": "t2",
             "printers": {"label": "Godex 2"}},
        ]})
        configs = trabajos_sheet.load_sheet_configs()
        self.assertEqual([c["id"] for c in configs], ["principal", "otra-planilla"])
        self.assertEqual(configs[1]["printers"], {"label": "Godex 2", "order": ""})

    def test_missing_token_is_an_error(self):
        self.write({"sheets": [{"id": "x", "url": "https://a/exec"}]})
        with self.assertRaisesRegex(RuntimeError, "no tiene url y token"):
            trabajos_sheet.load_sheet_configs()

    def test_registry_keeps_one_instance_per_sheet(self):
        self.write({"sheets": [
            {"id": "principal", "url": "https://a/exec", "token": "t1"},
            {"id": "otra", "url": "https://b/exec", "token": "t2"},
        ]})
        registry = trabajos_sheet.TrabajosSheets()
        self.assertIs(registry.get(), registry.get("principal"))
        self.assertEqual(registry.get("otra")._load_config()["url"], "https://b/exec")
        self.assertEqual(registry.list(), [{"id": "principal", "name": "principal"}, {"id": "otra", "name": "otra"}])
        with self.assertRaises(KeyError):
            registry.get("no-existe")

    def test_state_log_is_split_by_sheet(self):
        entries = [{"order": "viejo"}, {"sheet": "principal", "order": "S1"}, {"sheet": "otra", "order": "S2"}]
        with patch.object(trabajos_sheet, "_read_state_log", return_value=entries):
            self.assertEqual([e["order"] for e in TrabajosSheet("principal").state_log()], ["S1", "viejo"])
            self.assertEqual([e["order"] for e in TrabajosSheet("otra").state_log()], ["S2"])


if __name__ == "__main__":
    unittest.main()
