"""
Endpoints del tablero de plata pendiente: cobranzas y ventas sin facturar.
Solo lectura sobre Odoo.
"""

from __future__ import annotations

import asyncio
import csv
import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from account_statement_pdf import build_statement_filename, generate_statement_pdf
from company_branding import get_branding
from receivables_monitor import BUCKETS, OVERDUE_BUCKETS, receivables_monitor

router = APIRouter(prefix="/api/receivables", tags=["receivables"])


class ReceivablesConfigRequest(BaseModel):
    auto_refresh_enabled: Optional[bool] = None
    refresh_interval_minutes: Optional[int] = None
    stale_uninvoiced_days: Optional[int] = None
    whatsapp_template: Optional[str] = None
    company_name: Optional[str] = None


def _matches(row: Dict[str, Any], needle: str, keys: List[str]) -> bool:
    if not needle:
        return True
    return needle in " ".join(str(row.get(key) or "") for key in keys).lower()


def _filter_clients(clients: List[Dict[str, Any]], search: str, view: str, min_days: int) -> List[Dict[str, Any]]:
    needle = str(search or "").strip().lower()
    result = []
    for client in clients:
        if view == "overdue" and client.get("overdue", 0) <= 0:
            continue
        if view == "balance" and client.get("balance", 0) <= 0:
            continue
        if min_days and int(client.get("max_days_overdue") or 0) < min_days:
            continue
        if not _matches(client, needle, ["name", "vat", "phone", "email"]):
            continue
        result.append(client)
    return result


def _csv_response(header: List[str], rows: List[List[Any]], filename: str) -> StreamingResponse:
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(header)
    for row in rows:
        writer.writerow(
            [f"{value:.2f}".replace(".", ",") if isinstance(value, float) else ("" if value is None else value) for value in row]
        )
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return await asyncio.to_thread(receivables_monitor.load_config)


@router.post("/config")
async def save_config(request: ReceivablesConfigRequest) -> Dict[str, Any]:
    updates = {k: v for k, v in request.dict().items() if v is not None}
    return await asyncio.to_thread(receivables_monitor.save_config, updates)


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return await asyncio.to_thread(receivables_monitor.get_status)


@router.post("/refresh")
async def refresh() -> Dict[str, Any]:
    try:
        snapshot = await asyncio.to_thread(receivables_monitor.refresh)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "No se pudo actualizar cobranzas")
    return {"generated_at": snapshot.get("generated_at"), "summary": snapshot.get("summary", {})}


@router.get("/clients")
async def list_clients(
    search: str = "",
    view: str = Query("overdue", pattern="^(overdue|balance|all)$"),
    min_days: int = Query(0, ge=0, le=3650),
    limit: int = Query(300, ge=1, le=5000),
) -> Dict[str, Any]:
    snapshot = await asyncio.to_thread(receivables_monitor.load_snapshot)
    clients = _filter_clients(snapshot.get("clients", []), search, view, min_days)
    return {
        "generated_at": snapshot.get("generated_at", ""),
        "as_of": snapshot.get("as_of", ""),
        "summary": snapshot.get("summary", {}),
        "last_error": snapshot.get("last_error", ""),
        "total": len(clients),
        "items": clients[:limit],
    }


def _client_and_invoices(snapshot: Dict[str, Any], partner_id: int):
    client = next((c for c in snapshot.get("clients", []) if c.get("partner_id") == partner_id), None)
    if client is None:
        raise HTTPException(status_code=404, detail="El cliente no tiene saldo abierto en el ultimo tablero")
    invoices = [inv for inv in snapshot.get("invoices", []) if inv.get("commercial_partner_id") == partner_id]
    invoices.sort(key=lambda inv: (inv.get("due_date") or "", inv.get("name") or ""))
    return client, invoices


@router.get("/clients/{partner_id}")
async def get_client(partner_id: int) -> Dict[str, Any]:
    snapshot = await asyncio.to_thread(receivables_monitor.load_snapshot)
    client, invoices = _client_and_invoices(snapshot, partner_id)
    return {"client": client, "invoices": invoices}


@router.get("/clients/{partner_id}/statement.pdf")
async def get_statement(partner_id: int) -> Response:
    snapshot = await asyncio.to_thread(receivables_monitor.load_snapshot)
    client, invoices = _client_and_invoices(snapshot, partner_id)
    as_of = snapshot.get("as_of", "")
    branding = await asyncio.to_thread(get_branding)
    pdf = await asyncio.to_thread(
        generate_statement_pdf, client, invoices, snapshot.get("company_name", ""), as_of, branding
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{build_statement_filename(client, as_of)}"'},
    )


@router.get("/clients-export")
async def export_clients(search: str = "", view: str = "overdue", min_days: int = 0) -> StreamingResponse:
    snapshot = await asyncio.to_thread(receivables_monitor.load_snapshot)
    clients = _filter_clients(snapshot.get("clients", []), search, view, min_days)
    header = ["Cliente", "Documento", "Telefono", "Email", "Saldo", "Vencido", "Por vencer"]
    labels = dict(BUCKETS)
    header += [f"Vencido {labels[key]}" for key in OVERDUE_BUCKETS]
    header += ["Dias max. vencido", "Venc. mas antiguo", "Ultimo cobro"]
    rows = [
        [
            c["name"], c["vat"], c["phone"], c["email"], float(c["balance"]), float(c["overdue"]),
            float(c["buckets"]["por_vencer"]),
            *[float(c["buckets"][key]) for key in OVERDUE_BUCKETS],
            c["max_days_overdue"], c["oldest_due_date"], c["last_payment_date"],
        ]
        for c in clients
    ]
    return _csv_response(header, rows, "cobranzas.csv")


@router.get("/uninvoiced")
async def list_uninvoiced(
    search: str = "",
    view: str = Query("recent", pattern="^(recent|stale|all)$"),
    limit: int = Query(500, ge=1, le=5000),
) -> Dict[str, Any]:
    snapshot = await asyncio.to_thread(receivables_monitor.load_snapshot)
    needle = search.strip().lower()
    rows = [
        row
        for row in snapshot.get("uninvoiced", [])
        if (view == "all" or (view == "stale") == bool(row.get("stale")))
        and _matches(row, needle, ["name", "partner", "client_order_ref", "team", "salesperson"])
    ]
    return {
        "generated_at": snapshot.get("generated_at", ""),
        "summary": snapshot.get("summary", {}),
        "total": len(rows),
        "items": rows[:limit],
    }
