"""
Endpoints de la proyeccion de ventas y stock minimo de productos fabricados (solo lectura sobre Odoo).
"""

from __future__ import annotations

import asyncio
import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sales_projection import ALERT_STATUSES, STATUS_ORDER, sales_projection_monitor

router = APIRouter(prefix="/api/projection", tags=["projection"])

MONTH_NAMES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]


class ProjectionConfigRequest(BaseModel):
    auto_refresh_enabled: Optional[bool] = None
    refresh_interval_minutes: Optional[int] = None
    lead_time_days: Optional[int] = None
    service_level: Optional[int] = None
    base_months: Optional[int] = None
    target_coverage_days: Optional[int] = None
    use_seasonality: Optional[bool] = None
    min_active_months: Optional[int] = None
    make_to_order_categories: Optional[List[str]] = None
    make_to_order_codes: Optional[List[str]] = None
    make_to_stock_codes: Optional[List[str]] = None


def _filter_rows(
    rows: List[Dict[str, Any]],
    status: str = "",
    search: str = "",
    only_alerts: bool = False,
    abc: str = "",
    include_idle: bool = False,
) -> List[Dict[str, Any]]:
    wanted_status = str(status or "").strip().lower()
    wanted_abc = str(abc or "").strip().upper()
    needle = str(search or "").strip().lower()
    filtered = []
    for row in rows:
        if only_alerts and row.get("status") not in ALERT_STATUSES:
            continue
        if wanted_status and row.get("status") != wanted_status:
            continue
        # Los productos con BoM que nunca se vendieron son la mayoria: ocultos salvo que se pidan.
        if not wanted_status and not include_idle and row.get("status") == "sin_venta":
            continue
        if wanted_abc and row.get("abc") != wanted_abc:
            continue
        if needle:
            haystack = " ".join(str(row.get(key) or "") for key in ("default_code", "name", "category")).lower()
            if needle not in haystack:
                continue
        filtered.append(row)
    return filtered


def month_label(key: str) -> str:
    return f"{MONTH_NAMES[int(key[5:7]) - 1]}-{key[2:4]}"


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return await asyncio.to_thread(sales_projection_monitor.load_config)


@router.post("/config")
async def save_config(request: ProjectionConfigRequest) -> Dict[str, Any]:
    updates = {k: v for k, v in request.dict().items() if v is not None}
    return await asyncio.to_thread(sales_projection_monitor.save_config, updates)


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return await asyncio.to_thread(sales_projection_monitor.get_status)


@router.post("/refresh")
async def refresh() -> Dict[str, Any]:
    try:
        snapshot = await asyncio.to_thread(sales_projection_monitor.refresh)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "No se pudo actualizar la proyeccion")
    return {"generated_at": snapshot.get("generated_at"), "summary": snapshot.get("summary", {})}


@router.get("/report")
async def get_report(
    status: str = "",
    search: str = "",
    only_alerts: bool = False,
    abc: str = "",
    include_idle: bool = False,
    limit: int = Query(5000, ge=1, le=20000),
) -> Dict[str, Any]:
    if status and status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"Estado invalido: {status}")
    snapshot = await asyncio.to_thread(sales_projection_monitor.load_snapshot)
    rows = _filter_rows(snapshot.get("rows", []), status, search, only_alerts, abc, include_idle)
    return {
        "generated_at": snapshot.get("generated_at", ""),
        "history_since": snapshot.get("history_since", ""),
        "months": snapshot.get("months", []),
        "current_month": snapshot.get("current_month", ""),
        "forecast_months": snapshot.get("forecast_months", []),
        "base_months": snapshot.get("base_months", []),
        "config": snapshot.get("config", {}),
        "summary": snapshot.get("summary", {}),
        "last_error": snapshot.get("last_error", ""),
        "total": len(rows),
        "items": rows[:limit],
    }


def build_workbook(snapshot: Dict[str, Any], rows: List[Dict[str, Any]]) -> bytes:
    """Excel con dos hojas: el tablero ancho y los datos en formato largo para tabla dinamica."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    months = snapshot.get("months", [])
    current = snapshot.get("current_month", "")
    forecast_months = snapshot.get("forecast_months", [])
    bold = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="DDEBF7")
    forecast_fill = PatternFill("solid", fgColor="FFF2CC")

    wb = Workbook()
    ws = wb.active
    ws.title = "Proyeccion"
    fixed = [
        ("Estado", "status_label"), ("Modo", "mode"), ("ABC", "abc"), ("Referencia", "default_code"),
        ("Producto", "name"), ("Categoria", "category"),
    ]
    tail = [
        ("Venta 12m (u)", "qty_12m"), ("Venta 12m ($)", "amount_12m"), ("Precio prom. ($)", "avg_price"),
        ("Stock actual", "qty_available"), ("Comprometido", "outgoing_qty"), ("En fabricacion", "in_production"),
        ("Proyectado", "virtual_available"), ("Stock negativo", "negative_stock"), ("Minimo Odoo", "odoo_min_qty"),
        ("Stock seguridad", "safety_stock"), ("Minimo sugerido", "min_suggested"), ("Maximo sugerido", "max_suggested"),
        ("Cobertura (dias)", "coverage_days"), ("Fecha quiebre", "stockout_date"),
        ("Fabricar sugerido (u)", "suggested_qty"), ("Fabricar sugerido ($)", "suggested_amount"),
    ]
    headers = [label for label, _ in fixed]
    headers += [f"{month_label(m)} (u)" for m in months] + [f"{month_label(current)} en curso (u)"]
    headers += [f"Proy. {month_label(m)} (u)" for m in forecast_months]
    headers += [f"Proy. {month_label(m)} ($)" for m in forecast_months]
    headers += [label for label, _ in tail]
    ws.append(headers)
    first_forecast_col = len(fixed) + len(months) + 2
    for col, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font = bold
        is_forecast = first_forecast_col <= col < first_forecast_col + 2 * len(forecast_months)
        cell.fill = forecast_fill if is_forecast else header_fill

    for row in rows:
        values: List[Any] = [row.get(key) for _, key in fixed]
        values += [row["months"].get(m, {}).get("qty", 0) for m in months]
        values.append(row["months"].get(current, {}).get("qty", 0))
        values += [item["qty"] for item in row["forecast"]]
        values += [item["amount"] for item in row["forecast"]]
        for _, key in tail:
            value = row.get(key)
            values.append(("Si" if value else "") if key == "negative_stock" else value)
        ws.append(values)
    ws.freeze_panes = ws.cell(row=2, column=len(fixed) + 1)
    ws.auto_filter.ref = ws.dimensions
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 42 if headers[col - 1] == "Producto" else 13

    data = wb.create_sheet("Datos")
    data.append(["Referencia", "Producto", "Categoria", "ABC", "Modo", "Mes", "Tipo", "Unidades", "Pesos"])
    for cell in data[1]:
        cell.font = bold
        cell.fill = header_fill
    for row in rows:
        base = [row.get("default_code"), row.get("name"), row.get("category"), row.get("abc"), row.get("mode")]
        for month in months:
            values = row["months"].get(month, {})
            data.append(base + [month, "Real", values.get("qty", 0), values.get("amount", 0)])
        values = row["months"].get(current, {})
        data.append(base + [current, "Real (mes en curso)", values.get("qty", 0), values.get("amount", 0)])
        for item in row["forecast"]:
            data.append(base + [item["month"], "Proyeccion", item["qty"], item["amount"]])
    data.freeze_panes = "A2"
    data.auto_filter.ref = data.dimensions
    for col, width in zip("ABCDEFGHI", (16, 42, 30, 6, 8, 9, 20, 12, 14)):
        data.column_dimensions[col].width = width

    notes = wb.create_sheet("Parametros")
    config = snapshot.get("config", {})
    for label, value in (
        ("Generado", snapshot.get("generated_at", "")),
        ("Lead time (dias)", config.get("lead_time_days")),
        ("Nivel de servicio (%)", config.get("service_level")),
        ("Meses del promedio", ", ".join(snapshot.get("base_months", []))),
        ("Cobertura objetivo (dias)", config.get("target_coverage_days")),
        ("Estacionalidad", "Si" if config.get("use_seasonality") else "No"),
        ("Meses con venta para ser 'a stock'", config.get("min_active_months")),
        ("", ""),
        ("Nota", "Venta = lo pedido en pedidos confirmados (sin impuestos, en pesos). Informativo: no modifica Odoo."),
    ):
        notes.append([label, value])
    notes.column_dimensions["A"].width = 36
    notes.column_dimensions["B"].width = 90

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@router.get("/export")
async def export_report(
    status: str = "",
    search: str = "",
    only_alerts: bool = False,
    abc: str = "",
    include_idle: bool = False,
) -> StreamingResponse:
    snapshot = await asyncio.to_thread(sales_projection_monitor.load_snapshot)
    rows = _filter_rows(snapshot.get("rows", []), status, search, only_alerts, abc, include_idle)
    content = await asyncio.to_thread(build_workbook, snapshot, rows)
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="proyeccion_ventas.xlsx"'},
    )
