"""
Resumen "Hoy": junta en un solo llamado lo pendiente de cada modulo.

Usa los snapshots y estados locales que ya mantienen los otros modulos y solo
consulta Odoo en vivo para entregas/recepciones atrasadas y actividades (con
cache corta). Cada seccion falla por separado: un error en una no rompe la pagina.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date, datetime
from typing import Any, Callable, Dict

from fastapi import APIRouter

from odoo_integration import odoo_integration

router = APIRouter(prefix="/api/today", tags=["today"])

ODOO_ALERTS_TTL_SECONDS = 120
_odoo_alerts_cache: Dict[str, Any] = {"at": 0.0, "day": "", "data": None}


def _local_day(timestamp: Any) -> str:
    try:
        return datetime.fromisoformat(str(timestamp)).astimezone().date().isoformat()
    except ValueError:
        return ""


def _shipments_section() -> Dict[str, Any]:
    from administrado_endpoints import PRINT_STATE_LOCK, _load_print_state

    with PRINT_STATE_LOCK:
        history = list((_load_print_state().get("history") or []))
    today = date.today().isoformat()
    todays = [item for item in history if _local_day(item.get("timestamp")) == today]
    failures = [item for item in todays if not item.get("success")]
    last = max((item.get("timestamp") or "" for item in todays), default="")
    return {
        "printed_today": len({item.get("envio_id") for item in todays if item.get("success")}),
        "failed_today": len(failures),
        "last_print_at": last,
        "recent_failures": [
            {"envio_id": item.get("envio_id"), "error": item.get("error"), "timestamp": item.get("timestamp")}
            for item in failures[-5:]
        ],
    }


def _pos_section() -> Dict[str, Any]:
    from pos_reconciliation_worker import pos_reconciliation_worker

    status = pos_reconciliation_worker.get_status()
    status.pop("recent_events", None)
    return status


def _stock_section() -> Dict[str, Any]:
    from replenishment_monitor import replenishment_monitor

    status = replenishment_monitor.get_status()
    status.pop("config", None)
    return status


def _receivables_section() -> Dict[str, Any]:
    from receivables_monitor import receivables_monitor

    snapshot = receivables_monitor.load_snapshot()
    # Los 5 clientes con mas vencido: es donde una llamada mueve mas plata.
    top = [
        {key: client.get(key) for key in ("partner_id", "name", "overdue", "max_days_overdue", "whatsapp_url")}
        for client in (snapshot.get("clients") or [])[:5]
        if client.get("overdue", 0) > 0
    ]
    return {
        "generated_at": snapshot.get("generated_at", ""),
        "summary": snapshot.get("summary", {}),
        "last_error": snapshot.get("last_error", ""),
        "top_clients": top,
    }


def _odoo_section(force: bool) -> Dict[str, Any]:
    if not odoo_integration.is_configured():
        raise ValueError("Odoo no esta configurado")
    today = date.today().isoformat()
    cache = _odoo_alerts_cache
    fresh = time.time() - cache["at"] < ODOO_ALERTS_TTL_SECONDS and cache["day"] == today
    if force or not fresh or cache["data"] is None:
        cache["data"] = odoo_integration.get_today_alerts(today)
        cache["at"] = time.time()
        cache["day"] = today
    return {**cache["data"], "fetched_at": datetime.fromtimestamp(cache["at"]).astimezone().isoformat()}


async def _safe(builder: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    try:
        return {"ok": True, **(await asyncio.to_thread(builder))}
    except Exception as exc:
        message = odoo_integration.humanize_exception(exc) if hasattr(odoo_integration, "humanize_exception") else str(exc)
        return {"ok": False, "error": message or "No disponible"}


@router.get("/summary")
async def summary(refresh: bool = False) -> Dict[str, Any]:
    shipments, pos, stock, receivables, odoo = await asyncio.gather(
        _safe(_shipments_section),
        _safe(_pos_section),
        _safe(_stock_section),
        _safe(_receivables_section),
        _safe(lambda: _odoo_section(refresh)),
    )
    return {
        "date": date.today().isoformat(),
        "generated_at": datetime.now().astimezone().isoformat(),
        "shipments": shipments,
        "pos": pos,
        "stock": stock,
        "receivables": receivables,
        "odoo": odoo,
    }
