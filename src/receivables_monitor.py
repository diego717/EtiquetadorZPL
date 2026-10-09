"""
Tablero de plata pendiente: cuentas por cobrar por cliente y ventas confirmadas
sin facturar. Solo lee Odoo y guarda un snapshot local; no registra cobros ni
envia mensajes (el link de WhatsApp lo abre el operador).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from odoo_integration import odoo_integration

logger = logging.getLogger(__name__)

BUCKETS: List[Tuple[str, str]] = [
    ("por_vencer", "Por vencer"),
    ("d1_30", "1-30 dias"),
    ("d31_60", "31-60 dias"),
    ("d61_90", "61-90 dias"),
    ("d91_180", "91-180 dias"),
    ("d180", "Mas de 180"),
]
OVERDUE_BUCKETS = [key for key, _ in BUCKETS if key != "por_vencer"]
CURRENCY_SYMBOLS = {"UYU": "$", "USD": "US$", "EUR": "EUR"}

DEFAULT_WHATSAPP_TEMPLATE = (
    "Hola {cliente}, te escribimos de {empresa}. Según nuestros registros hay "
    "{cantidad} factura(s) vencida(s) por {saldo}; la más antigua venció el {vencimiento}. "
    "¿Nos podrías confirmar la fecha de pago? Muchas gracias."
)


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


def _m2o(value: Any) -> Tuple[Optional[int], str]:
    if isinstance(value, (list, tuple)) and value:
        return (int(value[0]) if value[0] else None), str(value[1] if len(value) > 1 else "")
    return None, ""


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    # Odoo devuelve False para char vacios y a veces "" (ver res.partner.phone).
    return str(value).strip() if value not in (None, False) else ""


def _clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(number, max_value))


def default_config() -> Dict[str, Any]:
    return {
        "auto_refresh_enabled": False,
        "refresh_interval_minutes": 60,
        # Ordenes sin facturar mas viejas que esto se marcan para revisar/limpiar en Odoo.
        "stale_uninvoiced_days": 180,
        "whatsapp_template": DEFAULT_WHATSAPP_TEMPLATE,
        # Vacio = usa el nombre de la compania de Odoo.
        "company_name": "",
    }


def normalize_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    base = default_config()
    base.update({k: v for k, v in (raw or {}).items() if k in base})
    base["auto_refresh_enabled"] = bool(base["auto_refresh_enabled"])
    base["refresh_interval_minutes"] = _clamp_int(base["refresh_interval_minutes"], 60, 15, 1440)
    base["stale_uninvoiced_days"] = _clamp_int(base["stale_uninvoiced_days"], 180, 30, 3650)
    base["whatsapp_template"] = str(base["whatsapp_template"] or "").strip() or DEFAULT_WHATSAPP_TEMPLATE
    base["company_name"] = str(base["company_name"] or "").strip()
    return base


def bucket_for(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "por_vencer"
    if days_overdue <= 30:
        return "d1_30"
    if days_overdue <= 60:
        return "d31_60"
    if days_overdue <= 90:
        return "d61_90"
    if days_overdue <= 180:
        return "d91_180"
    return "d180"


def currency_code(value: Any) -> str:
    _, name = _m2o(value)
    return (name or "UYU").strip().upper()


def format_money(amount: float, currency: str = "UYU") -> str:
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    text = f"{abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if amount < 0 else ''}{symbol} {text}"


def whatsapp_number(*raw_numbers: Any) -> str:
    """Primer celular uruguayo valido en formato internacional sin '+', o "".

    Celulares UY: 09X XXX XXX (nacional) = 598 9X XXX XXX. Los fijos (2/4...)
    no suelen tener WhatsApp y se descartan.
    """
    for raw in raw_numbers:
        for chunk in re.split(r"[/,;|]| y | o ", _text(raw)):
            digits = re.sub(r"\D", "", chunk)
            if digits.startswith("00"):
                digits = digits[2:]
            if digits.startswith("598"):
                digits = digits[3:]
            digits = digits.lstrip("0")
            if len(digits) == 8 and digits.startswith("9"):
                return f"598{digits}"
    return ""


def _amounts_text(totals: Dict[str, float]) -> str:
    parts = [format_money(amount, code) for code, amount in sorted(totals.items()) if round(amount, 2)]
    return " y ".join(parts) if parts else format_money(0.0)


def _display_date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(value or "")


def build_whatsapp_message(template: str, client: Dict[str, Any], company: str) -> str:
    values = {
        "cliente": client.get("name") or "",
        "empresa": company or "",
        "cantidad": client.get("overdue_count") or client.get("invoice_count") or 0,
        "saldo": _amounts_text(client.get("overdue_by_currency") or client.get("balance_by_currency") or {}),
        "saldo_total": _amounts_text(client.get("balance_by_currency") or {}),
        "vencimiento": _display_date(client.get("oldest_due_date")),
    }
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        # Plantilla con una variable desconocida: no romper el tablero por eso.
        return DEFAULT_WHATSAPP_TEMPLATE.format(**values)


def build_invoice_rows(moves: Iterable[Dict[str, Any]], today: date, url_for: Any) -> List[Dict[str, Any]]:
    rows = []
    for move in moves:
        commercial_id, commercial_name = _m2o(move.get("commercial_partner_id"))
        partner_id, partner_name = _m2o(move.get("partner_id"))
        due = move.get("invoice_date_due") or move.get("invoice_date")
        try:
            days_overdue = (today - date.fromisoformat(str(due)[:10])).days if due else 0
        except ValueError:
            days_overdue = 0
        is_refund = move.get("move_type") == "out_refund"
        sign = -1.0 if is_refund else 1.0
        _, term = _m2o(move.get("invoice_payment_term_id"))
        _, salesperson = _m2o(move.get("invoice_user_id"))
        rows.append(
            {
                "id": move.get("id"),
                "name": move.get("name") or "",
                "kind": "refund" if is_refund else "invoice",
                "label": "Nota de crédito" if is_refund else "",
                "reference": "",
                "is_refund": is_refund,
                "commercial_partner_id": commercial_id or partner_id,
                "commercial_partner": commercial_name or partner_name,
                "partner_id": partner_id,
                "invoice_date": move.get("invoice_date") or "",
                "due_date": due or "",
                "days_overdue": max(0, days_overdue) if not is_refund else 0,
                "bucket": "por_vencer" if is_refund else bucket_for(days_overdue),
                "currency": currency_code(move.get("currency_id")),
                "amount_total": round(sign * _as_float(move.get("amount_total")), 2),
                "residual": round(sign * _as_float(move.get("amount_residual")), 2),
                # En moneda de la compania: permite sumar clientes con facturas USD y UYU.
                "residual_company": round(_as_float(move.get("amount_residual_signed")), 2),
                "payment_state": move.get("payment_state") or "",
                "payment_term": term,
                "salesperson": salesperson,
                "url": url_for("account.move", move.get("id")) if move.get("id") else "",
            }
        )
    return rows


def build_unapplied_rows(lines: Iterable[Dict[str, Any]], today: date, url_for: Any) -> List[Dict[str, Any]]:
    """Cobros/creditos sin aplicar y debitos manuales abiertos en deudores.

    Un credito se trata como una nota de credito (resta del saldo, sin
    vencimiento); un debito, como una factura que vence en ``date_maturity``.
    """
    rows = []
    for line in lines:
        company_amount = _as_float(line.get("amount_residual"))
        if not company_amount:
            continue
        is_credit = company_amount < 0
        commercial_id, commercial_name = _m2o(line.get("commercial_partner_id"))
        partner_id, partner_name = _m2o(line.get("partner_id"))
        move_id, move_name = _m2o(line.get("move_id"))
        due = line.get("date_maturity") or line.get("date")
        try:
            days_overdue = (today - date.fromisoformat(str(due)[:10])).days if due else 0
        except ValueError:
            days_overdue = 0
        currency = currency_code(line.get("currency_id"))
        residual = _as_float(line.get("amount_residual_currency")) if line.get("currency_id") else company_amount
        _, journal = _m2o(line.get("journal_id"))
        rows.append(
            {
                "id": move_id,
                "name": line.get("move_name") or move_name,
                "kind": "unapplied_credit" if is_credit else "unapplied_debit",
                "label": "Crédito a favor" if is_credit else "Ajuste",
                "reference": " · ".join(t for t in (_text(line.get("ref")) or _text(line.get("name")), journal) if t),
                "is_refund": is_credit,
                "commercial_partner_id": commercial_id or partner_id,
                "commercial_partner": commercial_name or partner_name,
                "partner_id": partner_id,
                "invoice_date": line.get("date") or "",
                "due_date": due or "",
                "days_overdue": 0 if is_credit else max(0, days_overdue),
                "bucket": "por_vencer" if is_credit else bucket_for(days_overdue),
                "currency": currency,
                "amount_total": round(residual, 2),
                "residual": round(residual, 2),
                "residual_company": round(company_amount, 2),
                "payment_state": "",
                "payment_term": "",
                "salesperson": "",
                "url": url_for("account.move", move_id) if move_id else "",
            }
        )
    return rows


def build_clients(
    invoices: List[Dict[str, Any]],
    partners: Dict[int, Dict[str, Any]],
    last_payments: Dict[int, Dict[str, Any]],
    config: Dict[str, Any],
    company_name: str,
    url_for: Any,
) -> List[Dict[str, Any]]:
    clients: Dict[int, Dict[str, Any]] = {}
    for invoice in invoices:
        key = invoice["commercial_partner_id"] or 0
        client = clients.get(key)
        if client is None:
            client = clients[key] = {
                "partner_id": key or None,
                "name": invoice["commercial_partner"] or "(sin cliente)",
                "invoice_count": 0,
                "overdue_count": 0,
                "balance": 0.0,
                "overdue": 0.0,
                "credits": 0.0,
                "buckets": {bucket: 0.0 for bucket, _ in BUCKETS},
                "balance_by_currency": {},
                "overdue_by_currency": {},
                "oldest_due_date": "",
                "max_days_overdue": 0,
                "invoice_partner_ids": set(),
                "salespeople": set(),
            }
        amount = invoice["residual_company"]
        client["balance"] += amount
        client["balance_by_currency"][invoice["currency"]] = (
            client["balance_by_currency"].get(invoice["currency"], 0.0) + invoice["residual"]
        )
        if invoice["partner_id"]:
            client["invoice_partner_ids"].add(invoice["partner_id"])
        if invoice["salesperson"]:
            client["salespeople"].add(invoice["salesperson"])
        if invoice["is_refund"]:
            client["credits"] += amount
            continue
        client["invoice_count"] += 1
        client["buckets"][invoice["bucket"]] += amount
        if invoice["bucket"] != "por_vencer":
            client["overdue_count"] += 1
            client["overdue"] += amount
            client["overdue_by_currency"][invoice["currency"]] = (
                client["overdue_by_currency"].get(invoice["currency"], 0.0) + invoice["residual"]
            )
            if not client["oldest_due_date"] or invoice["due_date"] < client["oldest_due_date"]:
                client["oldest_due_date"] = invoice["due_date"]
            client["max_days_overdue"] = max(client["max_days_overdue"], invoice["days_overdue"])

    result = []
    for key, client in clients.items():
        commercial = partners.get(key, {})
        contacts = [commercial] + [partners.get(pid, {}) for pid in sorted(client["invoice_partner_ids"]) if pid != key]
        phone = next((_text(c.get("mobile")) or _text(c.get("phone")) for c in contacts if _text(c.get("mobile")) or _text(c.get("phone"))), "")
        email = next((_text(c.get("email")) for c in contacts if _text(c.get("email"))), "")
        whatsapp = whatsapp_number(*[value for c in contacts for value in (c.get("mobile"), c.get("phone"))])
        payment = last_payments.get(key) or {}
        row = {
            "partner_id": client["partner_id"],
            "name": client["name"],
            "vat": _text(commercial.get("vat")),
            "phone": phone,
            "email": email,
            "whatsapp_number": whatsapp,
            "salespeople": sorted(client["salespeople"]),
            "invoice_count": client["invoice_count"],
            "overdue_count": client["overdue_count"],
            "balance": round(client["balance"], 2),
            "overdue": round(client["overdue"], 2),
            "credits": round(client["credits"], 2),
            "buckets": {bucket: round(value, 2) for bucket, value in client["buckets"].items()},
            "balance_by_currency": {k: round(v, 2) for k, v in client["balance_by_currency"].items()},
            "overdue_by_currency": {k: round(v, 2) for k, v in client["overdue_by_currency"].items()},
            "oldest_due_date": client["oldest_due_date"],
            "max_days_overdue": client["max_days_overdue"],
            "last_payment_date": payment.get("date") or "",
            "last_payment_amount": payment.get("amount"),
            "last_payment_currency": payment.get("currency") or "",
            "url": url_for("res.partner", key) if key else "",
        }
        message = build_whatsapp_message(config["whatsapp_template"], row, config["company_name"] or company_name)
        row["whatsapp_message"] = message
        row["whatsapp_url"] = f"https://wa.me/{whatsapp}?text={quote(message)}" if whatsapp and row["overdue"] > 0 else ""
        result.append(row)

    result.sort(key=lambda c: (-c["overdue"], -c["balance"], c["name"]))
    return result


def is_cancelled_by_credit_note(order: Dict[str, Any]) -> bool:
    """La orden se facturo y una nota de credito anulo todo lo facturado.

    Odoo descuenta la nota de credito de lo facturado y vuelve a mostrar la
    orden como "a facturar", aunque la venta ya se anulo. Una nota de credito
    parcial no la oculta: queda un saldo que si podria facturarse.
    """
    invoiced = _as_float(order.get("invoiced_total"))
    refunded = _as_float(order.get("refunded_total"))
    return invoiced > 0 and refunded >= invoiced - 0.01


def build_uninvoiced(orders: Iterable[Dict[str, Any]], today: date, stale_days: int, url_for: Any) -> List[Dict[str, Any]]:
    rows = []
    for order in orders:
        order_date = str(order.get("date_order") or "")[:10]
        try:
            age = (today - date.fromisoformat(order_date)).days
        except ValueError:
            age = 0
        _, partner = _m2o(order.get("partner_id"))
        _, team = _m2o(order.get("team_id"))
        _, salesperson = _m2o(order.get("user_id"))
        to_invoice = order.get("amount_to_invoice")
        amount_to_invoice = _as_float(to_invoice if to_invoice is not None else order.get("amount_total"))
        if amount_to_invoice <= 0.005:
            # Odoo marca "a facturar" ordenes en cero o con devoluciones pendientes:
            # no hay plata para cobrar, solo ruido en este tablero.
            continue
        if is_cancelled_by_credit_note(order):
            continue
        rows.append(
            {
                "id": order.get("id"),
                "name": order.get("name") or "",
                "date_order": order_date,
                "age_days": max(0, age),
                "stale": age > stale_days,
                "partner": partner,
                "team": team,
                "salesperson": salesperson,
                "client_order_ref": _text(order.get("client_order_ref")),
                "currency": currency_code(order.get("currency_id")),
                "amount_total": round(_as_float(order.get("amount_total")), 2),
                "amount_to_invoice": round(amount_to_invoice, 2),
                "url": url_for("sale.order", order.get("id")) if order.get("id") else "",
            }
        )
    rows.sort(key=lambda r: (r["stale"], -r["age_days"]))
    return rows


def summarize(clients: List[Dict[str, Any]], invoices: List[Dict[str, Any]], uninvoiced: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    week_ago = (today - timedelta(days=7)).isoformat()
    today_iso = today.isoformat()
    newly_overdue = [
        inv for inv in invoices
        if not inv["is_refund"] and inv["bucket"] != "por_vencer" and week_ago <= inv["due_date"] < today_iso
    ]
    due_this_week = [
        inv for inv in invoices
        if not inv["is_refund"] and today_iso <= inv["due_date"] <= (today + timedelta(days=7)).isoformat()
    ]
    recent_uninvoiced = [row for row in uninvoiced if not row["stale"]]
    buckets = {bucket: 0.0 for bucket, _ in BUCKETS}
    for client in clients:
        for bucket, value in client["buckets"].items():
            buckets[bucket] += value
    total_overdue = sum(c["overdue"] for c in clients)
    top5 = sum(c["overdue"] for c in clients[:5])
    return {
        "clients_with_balance": sum(1 for c in clients if c["balance"] > 0),
        "clients_overdue": sum(1 for c in clients if c["overdue"] > 0),
        "total_balance": round(sum(c["balance"] for c in clients), 2),
        "total_overdue": round(total_overdue, 2),
        "overdue_invoices": sum(c["overdue_count"] for c in clients),
        "buckets": {k: round(v, 2) for k, v in buckets.items()},
        "top5_share": round(top5 / total_overdue * 100, 1) if total_overdue > 0 else 0.0,
        "newly_overdue_count": len(newly_overdue),
        "newly_overdue_amount": round(sum(inv["residual_company"] for inv in newly_overdue), 2),
        "due_this_week_count": len(due_this_week),
        "due_this_week_amount": round(sum(inv["residual_company"] for inv in due_this_week), 2),
        "uninvoiced_recent_count": len(recent_uninvoiced),
        "uninvoiced_recent_amount": round(sum(r["amount_to_invoice"] for r in recent_uninvoiced if r["currency"] == "UYU"), 2),
        "uninvoiced_stale_count": len(uninvoiced) - len(recent_uninvoiced),
    }


class ReceivablesMonitor:
    def __init__(self, odoo: Any = None) -> None:
        self.odoo = odoo or odoo_integration
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.config_path = _resolve_state_path("receivables_config.json")
        self.snapshot_path = _resolve_state_path("receivables_snapshot.json")

    def load_config(self) -> Dict[str, Any]:
        raw: Dict[str, Any] = {}
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except Exception as exc:
                logger.warning("No se pudo leer config de cobranzas: %s", exc)
        return normalize_config(raw)

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        config = self.load_config()
        config.update(updates or {})
        config = normalize_config(config)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=True)
        return config

    def load_snapshot(self) -> Dict[str, Any]:
        if not self.snapshot_path.exists():
            return {}
        try:
            with open(self.snapshot_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            logger.warning("No se pudo leer snapshot de cobranzas: %s", exc)
            return {}

    def _save_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.snapshot_path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=1, ensure_ascii=True)

    def refresh(self, today: Optional[date] = None) -> Dict[str, Any]:
        """Recalcula el tablero desde Odoo. Nunca escribe en Odoo."""
        if not self.odoo.is_configured():
            raise ValueError("Odoo no esta configurado")
        if not self._refresh_lock.acquire(blocking=False):
            raise RuntimeError("Ya hay una actualizacion de cobranzas en curso")
        try:
            today = today or date.today()
            config = self.load_config()
            data = self.odoo.get_receivables_data((today - timedelta(days=730)).isoformat())
            orders = self.odoo.get_uninvoiced_sale_orders()
            url_for = self.odoo.record_url

            invoices = build_invoice_rows(data["moves"], today, url_for)
            invoices += build_unapplied_rows(data.get("unapplied_lines") or [], today, url_for)
            clients = build_clients(
                invoices,
                {int(k): v for k, v in (data.get("partners") or {}).items()},
                {int(k): v for k, v in (data.get("last_payments") or {}).items()},
                config,
                data.get("company_name") or "",
                url_for,
            )
            uninvoiced = build_uninvoiced(orders, today, config["stale_uninvoiced_days"], url_for)
            snapshot = {
                "generated_at": _utc_now_iso(),
                "as_of": today.isoformat(),
                "company_name": config["company_name"] or data.get("company_name") or "",
                "summary": summarize(clients, invoices, uninvoiced, today),
                "clients": clients,
                "invoices": invoices,
                "uninvoiced": uninvoiced,
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
            "config": self.load_config(),
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="receivables-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _is_due(self, config: Dict[str, Any]) -> bool:
        generated_at = self.load_snapshot().get("generated_at")
        if not generated_at:
            return True
        try:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(generated_at)).total_seconds()
        except ValueError:
            return True
        return elapsed >= config["refresh_interval_minutes"] * 60

    def _run_loop(self) -> None:
        self._stop_event.wait(40)
        while not self._stop_event.is_set():
            try:
                config = self.load_config()
                if config["auto_refresh_enabled"] and self.odoo.is_configured() and self._is_due(config):
                    self.refresh()
            except Exception as exc:
                logger.warning("Fallo la actualizacion automatica de cobranzas: %s", exc)
            self._stop_event.wait(60)


receivables_monitor = ReceivablesMonitor()
