"""
Endpoints del monitor de reposicion (solo lectura sobre Odoo).
"""

from __future__ import annotations

import asyncio
import csv
import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from replenishment_monitor import STATUS_ORDER, replenishment_monitor

router = APIRouter(prefix="/api/replenishment", tags=["replenishment"])

ALERT_STATUSES = {"quiebre", "bajo_minimo", "cobertura_baja"}


class ReplenishmentConfigRequest(BaseModel):
    auto_refresh_enabled: Optional[bool] = None
    refresh_interval_minutes: Optional[int] = None
    history_days: Optional[int] = None
    low_coverage_days: Optional[int] = None
    target_coverage_days: Optional[int] = None
    default_min_qty: Optional[float] = None
    max_products: Optional[int] = None


def _filter_rows(
    rows: List[Dict[str, Any]],
    status: str,
    search: str,
    only_alerts: bool,
) -> List[Dict[str, Any]]:
    wanted_status = str(status or "").strip().lower()
    needle = str(search or "").strip().lower()
    filtered = []
    for row in rows:
        if only_alerts and row.get("status") not in ALERT_STATUSES:
            continue
        if wanted_status and row.get("status") != wanted_status:
            continue
        if needle:
            haystack = " ".join(
                str(row.get(key) or "") for key in ("default_code", "barcode", "name", "category")
            ).lower()
            if needle not in haystack:
                continue
        filtered.append(row)
    return filtered


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return await asyncio.to_thread(replenishment_monitor.load_config)


@router.post("/config")
async def save_config(request: ReplenishmentConfigRequest) -> Dict[str, Any]:
    updates = {k: v for k, v in request.dict().items() if v is not None}
    return await asyncio.to_thread(replenishment_monitor.save_config, updates)


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return await asyncio.to_thread(replenishment_monitor.get_status)


@router.post("/refresh")
async def refresh() -> Dict[str, Any]:
    try:
        snapshot = await asyncio.to_thread(replenishment_monitor.refresh)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "No se pudo actualizar el tablero")
    return {
        "generated_at": snapshot.get("generated_at"),
        "summary": snapshot.get("summary", {}),
    }


@router.get("/report")
async def get_report(
    status: str = "",
    search: str = "",
    only_alerts: bool = False,
    limit: int = Query(500, ge=1, le=20000),
) -> Dict[str, Any]:
    if status and status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"Estado invalido: {status}")
    snapshot = await asyncio.to_thread(replenishment_monitor.load_snapshot)
    rows = _filter_rows(snapshot.get("rows", []), status, search, only_alerts)
    return {
        "generated_at": snapshot.get("generated_at", ""),
        "history_since": snapshot.get("history_since", ""),
        "reorder_rules_available": snapshot.get("reorder_rules_available", False),
        "truncated": snapshot.get("truncated", False),
        "config": snapshot.get("config", {}),
        "summary": snapshot.get("summary", {}),
        "last_error": snapshot.get("last_error", ""),
        "total": len(rows),
        "items": rows[:limit],
    }


@router.get("/export")
async def export_report(status: str = "", search: str = "", only_alerts: bool = False) -> StreamingResponse:
    snapshot = await asyncio.to_thread(replenishment_monitor.load_snapshot)
    rows = _filter_rows(snapshot.get("rows", []), status, search, only_alerts)
    columns = [
        ("default_code", "Referencia"),
        ("name", "Producto"),
        ("category", "Categoria"),
        ("uom", "Unidad"),
        ("qty_available", "Stock actual"),
        ("outgoing_qty", "Ventas comprometidas"),
        ("incoming_qty", "Entradas pendientes"),
        ("virtual_available", "Stock proyectado"),
        ("min_qty", "Minimo"),
        ("max_qty", "Maximo"),
        ("daily_demand", "Consumo diario"),
        ("coverage_days", "Dias de cobertura"),
        ("status_label", "Estado"),
        ("suggested_qty", "Sugerido (informativo)"),
    ]
    buffer = io.StringIO()
    # BOM + ';' para que Excel en configuracion regional es-UY lo abra en columnas.
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([label for _, label in columns])
    for row in rows:
        values = []
        for key, _ in columns:
            value = row.get(key)
            if isinstance(value, float):
                value = f"{value:.2f}".replace(".", ",")
            values.append("" if value is None else value)
        writer.writerow(values)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reposicion.csv"'},
    )
