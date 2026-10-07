import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))

import replenishment_endpoints as endpoints
import replenishment_monitor as monitor_module
from replenishment_monitor import ReplenishmentMonitor, compute_rows, normalize_config, summarize


def _product(product_id, on_hand, projected, incoming=0.0, outgoing=0.0, code=""):
    return {
        "id": product_id,
        "default_code": code or f"P{product_id}",
        "name": f"Producto {product_id}",
        "qty_available": on_hand,
        "virtual_available": projected,
        "incoming_qty": incoming,
        "outgoing_qty": outgoing,
    }


CONFIG = normalize_config({"history_days": 30, "low_coverage_days": 14, "target_coverage_days": 30})


class TestComputeRows(unittest.TestCase):
    def _row(self, product, rules=None, delivered=None, config=CONFIG):
        return compute_rows([product], rules, delivered or {}, config)[0]

    def test_negative_projection_is_stockout(self):
        row = self._row(_product(1, on_hand=2, projected=-3, outgoing=5))
        self.assertEqual(row["status"], "quiebre")
        self.assertGreater(row["suggested_qty"], 0)

    def test_projection_below_odoo_rule_minimum(self):
        row = self._row(
            _product(1, on_hand=8, projected=8),
            rules={1: {"min_qty": 10.0, "max_qty": 40.0, "rules": 1}},
            delivered={1: 3.0},
        )
        self.assertEqual(row["status"], "bajo_minimo")
        self.assertEqual(row["min_source"], "regla_odoo")
        # Con regla, el sugerido completa hasta el maximo.
        self.assertEqual(row["suggested_qty"], 32.0)

    def test_coverage_uses_projected_stock_and_daily_demand(self):
        # 60 entregados en 30 dias = 2/dia; proyectado 20 -> 10 dias.
        row = self._row(_product(1, on_hand=25, projected=20, outgoing=5), delivered={1: 60.0})
        self.assertEqual(row["daily_demand"], 2.0)
        self.assertEqual(row["coverage_days"], 10.0)
        self.assertEqual(row["status"], "cobertura_baja")
        # Sin maximo: apunta a 30 dias de cobertura (60) menos el proyectado (20).
        self.assertEqual(row["suggested_qty"], 40.0)

    def test_healthy_product_has_no_suggestion(self):
        row = self._row(_product(1, on_hand=100, projected=100), delivered={1: 30.0})
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["coverage_days"], 100.0)
        self.assertEqual(row["suggested_qty"], 0.0)

    def test_product_without_demand_or_minimum_is_idle(self):
        row = self._row(_product(1, on_hand=0, projected=0))
        self.assertEqual(row["status"], "sin_movimiento")
        self.assertIsNone(row["coverage_days"])

    def test_default_minimum_applies_when_rules_are_unreadable(self):
        config = normalize_config({"default_min_qty": 5})
        row = self._row(_product(1, on_hand=3, projected=3), rules=None, config=config)
        self.assertEqual(row["status"], "bajo_minimo")
        self.assertEqual(row["min_source"], "default")

    def test_returns_exceeding_deliveries_do_not_create_negative_demand(self):
        row = self._row(_product(1, on_hand=10, projected=10), delivered={1: -4.0})
        self.assertEqual(row["daily_demand"], 0.0)

    def test_rows_are_sorted_by_urgency_and_summarized(self):
        rows = compute_rows(
            [
                _product(1, on_hand=100, projected=100),
                _product(2, on_hand=0, projected=-1, outgoing=1),
                _product(3, on_hand=5, projected=5),
            ],
            {3: {"min_qty": 10.0, "max_qty": 0.0, "rules": 1}},
            {1: 30.0},
            CONFIG,
        )
        self.assertEqual([row["product_id"] for row in rows], [2, 3, 1])
        summary = summarize(rows)
        self.assertEqual(summary["alertas"], 2)
        self.assertEqual(summary["total"], 3)

    def test_config_is_clamped(self):
        config = normalize_config({"refresh_interval_minutes": 1, "history_days": 0, "unknown": 1})
        self.assertEqual(config["refresh_interval_minutes"], 15)
        self.assertEqual(config["history_days"], 7)
        self.assertNotIn("unknown", config)


class _FakeOdoo:
    def __init__(self, fail=False):
        self.fail = fail
        self.since = None

    def is_configured(self):
        return True

    def humanize_exception(self, exc):
        return str(exc)

    def get_replenishment_products(self, max_products=5000):
        if self.fail:
            raise ValueError("Odoo caido")
        return [_product(1, on_hand=1, projected=1), _product(2, on_hand=50, projected=50)]

    def get_reorder_rules(self):
        return {1: {"min_qty": 4.0, "max_qty": 10.0, "rules": 1}}

    def get_customer_delivered_quantities(self, since_date):
        self.since = since_date
        return {2: 30.0}


class TestReplenishmentMonitor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self.patcher = patch.object(
            monitor_module, "_resolve_state_path", lambda name: tmp_path / name
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_refresh_saves_snapshot_without_writing_to_odoo(self):
        odoo = _FakeOdoo()
        monitor = ReplenishmentMonitor(odoo=odoo)
        snapshot = monitor.refresh()
        self.assertEqual(snapshot["summary"]["bajo_minimo"], 1)
        self.assertTrue(snapshot["reorder_rules_available"])
        self.assertEqual(monitor.load_snapshot()["generated_at"], snapshot["generated_at"])
        self.assertIsNotNone(odoo.since)

    def test_failed_refresh_keeps_previous_rows_and_records_error(self):
        odoo = _FakeOdoo()
        monitor = ReplenishmentMonitor(odoo=odoo)
        monitor.refresh()
        odoo.fail = True
        with self.assertRaises(ValueError):
            monitor.refresh()
        snapshot = monitor.load_snapshot()
        self.assertEqual(len(snapshot["rows"]), 2)
        self.assertIn("Odoo caido", snapshot["last_error"])

    def test_report_endpoint_filters_alerts_and_search(self):
        monitor = ReplenishmentMonitor(odoo=_FakeOdoo())
        monitor.refresh()
        with patch.object(endpoints, "replenishment_monitor", monitor):
            alerts = asyncio.run(endpoints.get_report(only_alerts=True, limit=500))
            searched = asyncio.run(endpoints.get_report(search="p2", limit=500))
        self.assertEqual([row["product_id"] for row in alerts["items"]], [1])
        self.assertEqual([row["product_id"] for row in searched["items"]], [2])


if __name__ == "__main__":
    unittest.main()
