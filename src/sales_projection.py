"""
Proyeccion de ventas y stock minimo de productos fabricados, calculada desde Odoo.

Solo lee datos (productos con lista de materiales, ordenes de fabricacion y lineas de
venta) y guarda un snapshot local. No crea ordenes ni toca reglas de reabastecimiento:
el minimo y la cantidad a fabricar son sugerencias para que un humano decida.

Metodo (simple y explicable a proposito):
- Venta mensual proyectada = promedio ponderado de los ultimos N meses completos
  (el mes mas reciente pesa mas), opcionalmente por un factor estacional del mismo
  mes del anio anterior cuando el producto vende de forma regular.
- Stock de seguridad = z(nivel de servicio) x desvio de la venta mensual x raiz(lead time / dias del mes).
- Minimo sugerido = consumo diario x lead time + stock de seguridad.
- Maximo sugerido = minimo + consumo diario x dias de cobertura objetivo.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from odoo_integration import odoo_integration

logger = logging.getLogger(__name__)

STATUS_ORDER = {"quiebre": 0, "fabricar": 1, "pedido_pendiente": 2, "atento": 3, "ok": 4, "a_pedido": 5, "sin_venta": 6}
STATUS_LABELS = {
    "quiebre": "Quiebre",
    "fabricar": "Fabricar",
    "pedido_pendiente": "Pedido sin cubrir",
    "atento": "Atento",
    "ok": "OK",
    "a_pedido": "A pedido",
    "sin_venta": "Sin venta",
}
ALERT_STATUSES = {"quiebre", "fabricar", "pedido_pendiente", "atento"}
SERVICE_LEVEL_Z = {90: 1.28, 95: 1.65, 98: 2.05, 99: 2.33}
DAYS_PER_MONTH = 30.4
DISPLAY_MONTHS = 12
FORECAST_MONTHS = 3


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
        "auto_refresh_enabled": False,
        "refresh_interval_minutes": 240,
        # Dias desde que se decide fabricar hasta que el producto esta en stock.
        "lead_time_days": 5,
        # Probabilidad de no quedar sin stock durante el lead time.
        "service_level": 95,
        # Meses completos que entran en el promedio ponderado de la proyeccion.
        "base_months": 6,
        # Cobertura que agrega el maximo sugerido por encima del minimo.
        "target_coverage_days": 30,
        "use_seasonality": True,
        # Si vendio en menos meses que esto (de los ultimos 12) se trata como fabricacion a pedido: sin minimo.
        "min_active_months": 3,
        # Correcciones manuales de la deteccion automatica.
        "make_to_order_categories": [],
        "make_to_order_codes": [],
        "make_to_stock_codes": [],
    }


def _as_text_list(value: Any) -> List[str]:
    if isinstance(value, str):
        value = value.replace("\n", ",").split(",")
    if not isinstance(value, (list, tuple)):
        return []
    seen: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text.upper() not in (s.upper() for s in seen):
            seen.append(text)
    return seen


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
    base["use_seasonality"] = bool(base["use_seasonality"])
    base["refresh_interval_minutes"] = _clamp_int(base["refresh_interval_minutes"], 240, 30, 1440)
    base["lead_time_days"] = _clamp_int(base["lead_time_days"], 5, 1, 120)
    base["base_months"] = _clamp_int(base["base_months"], 6, 2, 24)
    base["target_coverage_days"] = _clamp_int(base["target_coverage_days"], 30, 0, 365)
    base["min_active_months"] = _clamp_int(base["min_active_months"], 3, 1, 12)
    for key in ("make_to_order_categories", "make_to_order_codes", "make_to_stock_codes"):
        base[key] = _as_text_list(base[key])
    level = _clamp_int(base["service_level"], 95, 90, 99)
    # Solo niveles con z conocido: se redondea al mas cercano.
    base["service_level"] = min(SERVICE_LEVEL_Z, key=lambda known: abs(known - level))
    return base


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _shift_month(key: str, delta: int) -> str:
    year, month = int(key[:4]), int(key[5:7])
    index = year * 12 + (month - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_window(today: date) -> Dict[str, Any]:
    """Meses que maneja el tablero, relativos a `today`."""
    current = _month_key(today)
    complete = [_shift_month(current, -offset) for offset in range(24, 0, -1)]
    return {
        "current": current,
        # 24 meses completos: 12 se muestran y los 12 anteriores dan la estacionalidad.
        "complete": complete,
        "display": complete[-DISPLAY_MONTHS:],
        # Incluye el mes en curso: es el que define el consumo diario de hoy.
        "forecast": [_shift_month(current, offset) for offset in range(FORECAST_MONTHS)],
        "since": f"{complete[0]}-01",
    }


def _seasonal_factor(qty_by_month: Dict[str, float], target_month: str) -> Optional[float]:
    """Mismo mes del anio pasado / promedio mensual de ese anio, solo con venta regular."""
    # 12 meses (objetivo-17 .. objetivo-6): ya cerrados y centrados en el mismo mes del anio pasado.
    last_year = [_shift_month(target_month, -offset) for offset in range(17, 5, -1)]
    same_month = _shift_month(target_month, -12)
    values = [qty_by_month.get(month, 0.0) for month in last_year]
    if sum(1 for value in values if value > 0) < 9:
        return None
    average = sum(values) / len(values)
    if average <= 0:
        return None
    return max(0.5, min(2.0, qty_by_month.get(same_month, 0.0) / average))


def _replenishment_mode(product: Dict[str, Any], active_months: int, config: Dict[str, Any]) -> Tuple[str, str]:
    """("stock" | "pedido", origen). Lo manual por codigo gana sobre la categoria y sobre lo automatico."""
    code = str(product.get("default_code") or "").strip().upper()
    if code and code in {c.upper() for c in config.get("make_to_stock_codes") or []}:
        return "stock", "producto"
    if code and code in {c.upper() for c in config.get("make_to_order_codes") or []}:
        return "pedido", "producto"
    category = str(product.get("category") or "").upper()
    if any(fragment.upper() in category for fragment in config.get("make_to_order_categories") or []):
        return "pedido", "categoria"
    if active_months < int(config.get("min_active_months") or 3):
        return "pedido", "auto"
    return "stock", "auto"


def _assign_abc(rows: List[Dict[str, Any]]) -> None:
    total = sum(row["amount_12m"] for row in rows if row["amount_12m"] > 0)
    for row in rows:
        row["abc"] = "-"
    if total <= 0:
        return
    cumulative = 0.0
    for row in sorted((r for r in rows if r["amount_12m"] > 0), key=lambda r: -r["amount_12m"]):
        share_before = cumulative / total
        cumulative += row["amount_12m"]
        row["abc"] = "A" if share_before < 0.80 else ("B" if share_before < 0.95 else "C")


def compute_rows(
    products: List[Dict[str, Any]],
    sales: Dict[int, Dict[str, Dict[str, float]]],
    open_productions: Dict[int, Dict[str, Any]],
    reorder_rules: Optional[Dict[int, Dict[str, float]]],
    config: Dict[str, Any],
    today: date,
) -> List[Dict[str, Any]]:
    """Calcula proyeccion e indicadores de stock por producto (funcion pura)."""
    window = month_window(today)
    base_months = window["complete"][-int(config.get("base_months") or 6):]
    last_12 = window["complete"][-12:]
    lead_time = float(config.get("lead_time_days") or 5)
    target_days = float(config.get("target_coverage_days") or 0)
    z = SERVICE_LEVEL_Z.get(int(config.get("service_level") or 95), 1.65)
    use_seasonality = bool(config.get("use_seasonality", True))
    rules = reorder_rules or {}
    weights = list(range(1, len(base_months) + 1))

    rows: List[Dict[str, Any]] = []
    for product in products:
        product_id = product.get("id")
        by_month = sales.get(product_id, {}) if product_id is not None else {}
        qty_by_month = {month: _as_float(values.get("qty")) for month, values in by_month.items()}

        qty_12m = sum(qty_by_month.get(month, 0.0) for month in last_12)
        amount_12m = sum(_as_float(by_month.get(month, {}).get("amount")) for month in last_12)
        avg_price = amount_12m / qty_12m if qty_12m > 0 else _as_float(product.get("list_price"))

        base_qty = [qty_by_month.get(month, 0.0) for month in base_months]
        monthly_level = sum(w * q for w, q in zip(weights, base_qty)) / sum(weights) if weights else 0.0
        monthly_level = max(0.0, monthly_level)

        forecast = []
        for month in window["forecast"]:
            factor = _seasonal_factor(qty_by_month, month) if use_seasonality else None
            qty = monthly_level * (factor or 1.0)
            forecast.append(
                {
                    "month": month,
                    "qty": round(qty, 2),
                    "amount": round(qty * avg_price, 2),
                    "seasonal_factor": round(factor, 2) if factor is not None else None,
                }
            )

        series_12 = [qty_by_month.get(month, 0.0) for month in last_12]
        mean_12 = sum(series_12) / len(series_12)
        std_monthly = math.sqrt(sum((q - mean_12) ** 2 for q in series_12) / len(series_12))

        active_months = sum(1 for q in series_12 if q > 0)
        mode, mode_source = _replenishment_mode(product, active_months, config)
        make_to_stock = mode == "stock"

        daily_demand = (forecast[0]["qty"] if forecast else monthly_level) / DAYS_PER_MONTH
        safety_stock = z * std_monthly * math.sqrt(lead_time / DAYS_PER_MONTH) if daily_demand > 0 and make_to_stock else 0.0
        min_suggested = daily_demand * lead_time + safety_stock if make_to_stock else 0.0
        max_suggested = min_suggested + daily_demand * target_days if min_suggested > 0 else 0.0

        on_hand = _as_float(product.get("qty_available"))
        committed = _as_float(product.get("outgoing_qty"))
        production = open_productions.get(product_id, {}) if product_id is not None else {}
        in_production = _as_float(production.get("qty"))
        # Un stock negativo es un error de carga en Odoo (se vendio sin registrar la fabricacion):
        # se calcula como si hubiera 0 para no inflar lo sugerido.
        negative_stock = on_hand < 0
        # Los borradores todavia no suman en el proyectado de Odoo.
        projected = (
            _as_float(product.get("virtual_available"))
            - min(on_hand, 0.0)
            + _as_float(production.get("draft_qty"))
        )

        coverage_days: Optional[float] = None
        stockout_date = ""
        if daily_demand > 0 and make_to_stock:
            coverage_days = round(max(projected, 0.0) / daily_demand, 1)
            days_left = int(max(projected, 0.0) // daily_demand)
            stockout_date = (today + timedelta(days=days_left)).isoformat()

        has_demand = daily_demand > 0 or committed > 0
        if not make_to_stock:
            status = "pedido_pendiente" if projected < 0 else ("a_pedido" if has_demand or qty_12m > 0 else "sin_venta")
        elif has_demand and projected <= 0:
            status = "quiebre"
        elif daily_demand > 0 and projected < min_suggested:
            status = "fabricar"
        elif daily_demand > 0 and projected < min_suggested + daily_demand * lead_time:
            status = "atento"
        elif not has_demand:
            status = "sin_venta"
        else:
            status = "ok"

        suggested = 0.0
        if status == "pedido_pendiente":
            # A pedido: solo lo comprometido que no cubre el stock ni lo que ya se esta fabricando.
            suggested = float(math.ceil(-projected))
        elif status in {"quiebre", "fabricar"}:
            # El proyectado ya descuenta lo comprometido: se completa hasta el maximo sugerido.
            suggested = float(math.ceil(max(0.0, max_suggested - projected)))

        rule = rules.get(product_id) if product_id is not None else None
        rows.append(
            {
                "product_id": product_id,
                "default_code": product.get("default_code") or "",
                "name": product.get("name") or "",
                "category": product.get("category") or "",
                "uom": product.get("uom") or "",
                "months": {
                    month: {
                        "qty": round(qty_by_month.get(month, 0.0), 2),
                        "amount": round(_as_float(by_month.get(month, {}).get("amount")), 2),
                    }
                    for month in window["display"] + [window["current"]]
                },
                "forecast": forecast,
                "forecast_qty_total": round(sum(item["qty"] for item in forecast), 2),
                "forecast_amount_total": round(sum(item["amount"] for item in forecast), 2),
                "qty_12m": round(qty_12m, 2),
                "amount_12m": round(amount_12m, 2),
                "avg_price": round(avg_price, 2),
                "monthly_level": round(monthly_level, 2),
                "std_monthly": round(std_monthly, 2),
                "daily_demand": round(daily_demand, 3),
                "qty_available": round(on_hand, 2),
                "outgoing_qty": round(committed, 2),
                "incoming_qty": round(_as_float(product.get("incoming_qty")), 2),
                "virtual_available": round(projected, 2),
                "negative_stock": negative_stock,
                "mode": mode,
                "mode_source": mode_source,
                "active_months": active_months,
                "in_production": round(in_production, 2),
                "production_orders": production.get("orders", []),
                "next_production_date": production.get("next_date", ""),
                "odoo_min_qty": round(_as_float(rule.get("min_qty")), 2) if rule else None,
                "safety_stock": round(safety_stock, 2),
                "min_suggested": float(math.ceil(min_suggested)),
                "max_suggested": float(math.ceil(max_suggested)),
                "coverage_days": coverage_days,
                "stockout_date": stockout_date,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "suggested_qty": suggested,
                "suggested_amount": round(suggested * avg_price, 2),
            }
        )

    _assign_abc(rows)
    rows.sort(
        key=lambda row: (
            STATUS_ORDER.get(row["status"], 9),
            row["coverage_days"] if row["coverage_days"] is not None else float("inf"),
            -row["amount_12m"],
            row["default_code"] or row["name"],
        )
    )
    return rows


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {status: 0 for status in STATUS_ORDER}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    summary["total"] = len(rows)
    summary["alertas"] = sum(summary[status] for status in ALERT_STATUSES)
    summary["negative_stock"] = sum(1 for row in rows if row.get("negative_stock"))
    summary["amount_12m"] = round(sum(row["amount_12m"] for row in rows), 2)
    summary["forecast_amount_total"] = round(sum(row["forecast_amount_total"] for row in rows), 2)
    summary["suggested_amount"] = round(sum(row["suggested_amount"] for row in rows), 2)
    return summary


class SalesProjectionMonitor:
    def __init__(self, odoo: Any = None) -> None:
        self.odoo = odoo or odoo_integration
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.config_path = _resolve_state_path("sales_projection_config.json")
        self.snapshot_path = _resolve_state_path("sales_projection_snapshot.json")

    # ---- config ----
    def load_config(self) -> Dict[str, Any]:
        raw: Dict[str, Any] = {}
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except Exception as exc:
                logger.warning("No se pudo leer config de la proyeccion de ventas: %s", exc)
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
            logger.warning("No se pudo leer snapshot de proyeccion de ventas: %s", exc)
            return {}

    def _save_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.snapshot_path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=1, ensure_ascii=True)

    def refresh(self, today: Optional[date] = None) -> Dict[str, Any]:
        """Recalcula la proyeccion desde Odoo. Nunca escribe en Odoo."""
        if not self.odoo.is_configured():
            raise ValueError("Odoo no esta configurado")
        if not self._refresh_lock.acquire(blocking=False):
            raise RuntimeError("Ya hay una actualizacion de la proyeccion en curso")
        try:
            started_at = _utc_now_iso()
            today = today or date.today()
            config = self.load_config()
            window = month_window(today)

            products = self.odoo.get_manufactured_products()
            sales = self.odoo.get_monthly_sales([p["id"] for p in products if p.get("id") is not None], window["since"])
            open_productions = self.odoo.get_open_productions()
            reorder_rules = self.odoo.get_reorder_rules()

            rows = compute_rows(products, sales, open_productions, reorder_rules, config, today)
            snapshot = {
                "generated_at": _utc_now_iso(),
                "started_at": started_at,
                "today": today.isoformat(),
                "history_since": window["since"],
                "months": window["display"],
                "current_month": window["current"],
                "forecast_months": window["forecast"],
                "base_months": window["complete"][-config["base_months"]:],
                "config": config,
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
        self._thread = threading.Thread(target=self._run_loop, name="sales-projection-monitor", daemon=True)
        self._thread.start()
        logger.info("Monitor de proyeccion de ventas iniciado")

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
        # Espera inicial para no competir con el arranque de la API ni con el monitor de reposicion.
        self._stop_event.wait(90)
        while not self._stop_event.is_set():
            try:
                config = self.load_config()
                if config["auto_refresh_enabled"] and self.odoo.is_configured() and self._is_due(config):
                    self.refresh()
            except Exception as exc:
                logger.warning("Fallo la actualizacion automatica de la proyeccion de ventas: %s", exc)
            self._stop_event.wait(60)


sales_projection_monitor = SalesProjectionMonitor()
