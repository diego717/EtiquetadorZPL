"""
Monitor de reposicion: tablero informativo de stock calculado desde Odoo.

Solo lee datos (productos, reglas de reabastecimiento y entregas a clientes) y
guarda un snapshot local. No crea compras ni toca reglas de reabastecimiento:
la cantidad sugerida es orientativa para que un humano decida.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from odoo_integration import odoo_integration

logger = logging.getLogger(__name__)

STATUS_ORDER = {"quiebre": 0, "bajo_minimo": 1, "cobertura_baja": 2, "ok": 3, "sin_movimiento": 4}
STATUS_LABELS = {
    "quiebre": "Quiebre",
    "bajo_minimo": "Bajo minimo",
    "cobertura_baja": "Cobertura baja",
    "ok": "OK",
    "sin_movimiento": "Sin movimiento",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_state_path(filename: str) -> Path:
    try:
        from config_manager import config_manager

        return Path(config_manager.get_config_directory()) / filename
    except Exception:
        import os

        if os.name == "nt":
            base_dir = Path(os.environ.get("APPDATA", "."))
        else:
            base_dir = Path.home() / ".config"
        config_dir = base_dir / "EtiquetadorZPL"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / filename


def default_config() -> Dict[str, Any]:
    return {
        # El worker refresca solo si esta habilitado; el boton "Actualizar" siempre funciona.
        "auto_refresh_enabled": False,
        "refresh_interval_minutes": 60,
        # Dias de historia de entregas para estimar el consumo diario.
        "history_days": 30,
        # Por debajo de estos dias de cobertura el producto se marca "cobertura baja".
        "low_coverage_days": 14,
        # Cobertura objetivo para la cantidad sugerida cuando no hay regla con maximo.
        "target_coverage_days": 30,
        # Minimo que se aplica a productos sin regla de reabastecimiento (0 = sin minimo).
        "default_min_qty": 0,
        "max_products": 5000,
    }


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(number, max_value))


def normalize_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    base = default_config()
    base.update({k: v for k, v in (raw or {}).items() if k in base})
    base["auto_refresh_enabled"] = bool(base["auto_refresh_enabled"])
    base["refresh_interval_minutes"] = _clamp_int(base["refresh_interval_minutes"], 60, 15, 1440)
    base["history_days"] = _clamp_int(base["history_days"], 30, 7, 365)
    base["low_coverage_days"] = _clamp_int(base["low_coverage_days"], 14, 1, 365)
    base["target_coverage_days"] = _clamp_int(base["target_coverage_days"], 30, 1, 365)
    base["max_products"] = _clamp_int(base["max_products"], 5000, 1, 20000)
    base["default_min_qty"] = max(0.0, _as_float(base["default_min_qty"]))
    return base


def compute_rows(
    products: List[Dict[str, Any]],
    reorder_rules: Optional[Dict[int, Dict[str, float]]],
    delivered: Dict[int, float],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Calcula los indicadores de reposicion por producto (funcion pura)."""
    history_days = max(1, int(config.get("history_days") or 30))
    low_coverage_days = float(config.get("low_coverage_days") or 14)
    target_coverage_days = float(config.get("target_coverage_days") or 30)
    default_min_qty = _as_float(config.get("default_min_qty"))
    rules = reorder_rules or {}

    rows: List[Dict[str, Any]] = []
    for product in products:
        product_id = product.get("id")
        on_hand = _as_float(product.get("qty_available"))
        projected = _as_float(product.get("virtual_available"))
        incoming = _as_float(product.get("incoming_qty"))
        committed = _as_float(product.get("outgoing_qty"))

        rule = rules.get(product_id) if product_id is not None else None
        if rule:
            min_qty = _as_float(rule.get("min_qty"))
            max_qty = _as_float(rule.get("max_qty"))
            min_source = "regla_odoo"
        else:
            min_qty = default_min_qty
            max_qty = 0.0
            min_source = "default" if default_min_qty > 0 else ""

        delivered_qty = max(0.0, _as_float(delivered.get(product_id)))
        daily_demand = delivered_qty / history_days
        # La cobertura se mide sobre el proyectado: las ventas comprometidas ya
        # estan descontadas y las entradas pendientes ya estan sumadas.
        coverage_days: Optional[float]
        if daily_demand > 0:
            coverage_days = round(max(projected, 0.0) / daily_demand, 1)
        else:
            coverage_days = None

        has_demand = daily_demand > 0 or committed > 0
        if projected < 0 or (has_demand and projected <= 0):
            status = "quiebre"
        elif min_qty > 0 and projected < min_qty:
            status = "bajo_minimo"
        elif coverage_days is not None and coverage_days < low_coverage_days:
            status = "cobertura_baja"
        elif not has_demand and min_qty <= 0:
            status = "sin_movimiento"
        else:
            status = "ok"

        suggested = 0.0
        if status in {"quiebre", "bajo_minimo", "cobertura_baja"}:
            if max_qty > 0:
                target = max_qty
            else:
                target = max(min_qty, daily_demand * target_coverage_days)
            suggested = max(0.0, target - projected)

        rows.append(
            {
                "product_id": product_id,
                "default_code": product.get("default_code") or "",
                "barcode": product.get("barcode") or "",
                "name": product.get("name") or "",
                "category": product.get("category") or "",
                "uom": product.get("uom") or "",
                "qty_available": round(on_hand, 2),
                "outgoing_qty": round(committed, 2),
                "incoming_qty": round(incoming, 2),
                "virtual_available": round(projected, 2),
                "min_qty": round(min_qty, 2),
                "max_qty": round(max_qty, 2),
                "min_source": min_source,
                "delivered_qty": round(delivered_qty, 2),
                "daily_demand": round(daily_demand, 3),
                "coverage_days": coverage_days,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "suggested_qty": round(suggested, 2),
            }
        )

    rows.sort(
        key=lambda row: (
            STATUS_ORDER.get(row["status"], 9),
            row["coverage_days"] if row["coverage_days"] is not None else float("inf"),
            # A igual cobertura, primero lo que mas se vende.
            -row["daily_demand"],
            row["default_code"] or row["name"],
        )
    )
    return rows


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {status: 0 for status in STATUS_ORDER}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    summary["total"] = len(rows)
    summary["alertas"] = summary["quiebre"] + summary["bajo_minimo"] + summary["cobertura_baja"]
    return summary


class ReplenishmentMonitor:
    def __init__(self, odoo: Any = None) -> None:
        self.odoo = odoo or odoo_integration
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.config_path = _resolve_state_path("replenishment_config.json")
        self.snapshot_path = _resolve_state_path("replenishment_snapshot.json")

    # ---- config ----
    def load_config(self) -> Dict[str, Any]:
        raw: Dict[str, Any] = {}
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except Exception as exc:
                logger.warning("No se pudo leer config del monitor de reposicion: %s", exc)
        return normalize_config(raw)

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        config = self.load_config()
        config.update(updates or {})
        config = normalize_config(config)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=True)
        return config

    # ---- snapshot ----
    def load_snapshot(self) -> Dict[str, Any]:
        if not self.snapshot_path.exists():
            return {}
        try:
            with open(self.snapshot_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            logger.warning("No se pudo leer snapshot de reposicion: %s", exc)
            return {}

    def _save_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.snapshot_path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=1, ensure_ascii=True)

    def refresh(self) -> Dict[str, Any]:
        """Recalcula el tablero desde Odoo. Nunca escribe en Odoo."""
        if not self.odoo.is_configured():
            raise ValueError("Odoo no esta configurado")
        if not self._refresh_lock.acquire(blocking=False):
            raise RuntimeError("Ya hay una actualizacion del tablero en curso")
        try:
            started_at = _utc_now_iso()
            config = self.load_config()
            since = (date.today() - timedelta(days=config["history_days"])).isoformat()

            products = self.odoo.get_replenishment_products(max_products=config["max_products"])
            reorder_rules = self.odoo.get_reorder_rules()
            delivered = self.odoo.get_customer_delivered_quantities(since)

            rows = compute_rows(products, reorder_rules, delivered, config)
            snapshot = {
                "generated_at": _utc_now_iso(),
                "started_at": started_at,
                "history_since": since,
                "config": config,
                "reorder_rules_available": reorder_rules is not None,
                "truncated": len(products) >= config["max_products"],
                "summary": summarize(rows),
                "rows": rows,
                "last_error": "",
            }
            with self._lock:
                self._save_snapshot(snapshot)
            return snapshot
        except Exception as exc:
            with self._lock:
                previous = self.load_snapshot()
                previous["last_error"] = self.odoo.humanize_exception(exc) if hasattr(self.odoo, "humanize_exception") else str(exc)
                previous["last_error_at"] = _utc_now_iso()
                self._save_snapshot(previous)
            raise
        finally:
            self._refresh_lock.release()

    def get_status(self) -> Dict[str, Any]:
        snapshot = self.load_snapshot()
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "refreshing": self._refresh_lock.locked(),
            "generated_at": snapshot.get("generated_at", ""),
            "summary": snapshot.get("summary", {}),
            "last_error": snapshot.get("last_error", ""),
            "last_error_at": snapshot.get("last_error_at", ""),
            "config": self.load_config(),
        }

    # ---- worker ----
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="replenishment-monitor", daemon=True)
        self._thread.start()
        logger.info("Monitor de reposicion iniciado")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _is_due(self, config: Dict[str, Any]) -> bool:
        generated_at = self.load_snapshot().get("generated_at")
        if not generated_at:
            return True
        try:
            last = datetime.fromisoformat(generated_at)
        except ValueError:
            return True
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= config["refresh_interval_minutes"] * 60

    def _run_loop(self) -> None:
        # Pequena espera inicial para no competir con el arranque de la API.
        self._stop_event.wait(30)
        while not self._stop_event.is_set():
            try:
                config = self.load_config()
                if config["auto_refresh_enabled"] and self.odoo.is_configured() and self._is_due(config):
                    self.refresh()
            except Exception as exc:
                logger.warning("Fallo la actualizacion automatica del tablero de reposicion: %s", exc)
            self._stop_event.wait(60)


replenishment_monitor = ReplenishmentMonitor()
