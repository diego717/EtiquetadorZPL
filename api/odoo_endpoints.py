"""
Endpoints para integracion Odoo y automatizacion Odoo + Administrado.
"""

from __future__ import annotations

import asyncio
import csv
import io
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from odoo_automation import odoo_automation_worker
from odoo_integration import odoo_integration

router = APIRouter(prefix="/api/odoo", tags=["odoo"])


def _friendly_error(exc: Exception) -> str:
    return odoo_integration.humanize_exception(exc)


class OdooConfigRequest(BaseModel):
    enabled: bool = False
    base_url: str = ""
    database: str = ""
    username: str = ""
    password: str = ""
    report_name: str = "sale.report_saleorder"
    order_prefix: str = "ML "
    shipment_field: str = ""
    allowed_order_states: str = "draft,sent,sale"
    default_order_printer: str = "Expedicion"
    fallback_order_printer: str = ""
    default_order_copies: int = Field(default=1, ge=1, le=10)
    order_pdf_render_dpi: int = Field(default=300, ge=150, le=600)
    force_order_grayscale: bool = False
    default_label_printer: str = ""
    fallback_label_printer: str = ""
    default_label_copies: int = Field(default=1, ge=1, le=10)
    automation_enabled: bool = False
    automation_interval_seconds: int = Field(default=60, ge=15, le=3600)
    automation_sync_limit: int = Field(default=20, ge=1, le=50)
    automation_include_reprint: bool = False
    automation_order_to_label_delay_seconds: int = Field(default=1, ge=0, le=30)
    confirm_order_on_print: bool = False


class OdooSearchOrderRequest(BaseModel):
    envio_id: str


class OdooPrintOrderRequest(BaseModel):
    envio_id: str
    printer: str = ""
    copies: int = Field(default=1, ge=1, le=10)


class OdooSearchInvoicesRequest(BaseModel):
    date_from: str = ""
    date_to: str = ""
    limit: Optional[int] = None


class OdooOperatorUserRequest(BaseModel):
    app_username: str
    odoo_username: str
    odoo_password: str


class OdooRegisterPaymentRequest(BaseModel):
    invoice_id: int
    amount: float
    payment_date: str = ""
    journal_id: int
    memo: str = ""


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return odoo_integration.get_public_config()


@router.post("/config")
async def save_config(config: OdooConfigRequest) -> Dict[str, Any]:
    payload = config.dict()
    if not payload.get("password"):
        payload.pop("password", None)
    return odoo_integration.save_config(payload)


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return {
        "config": odoo_integration.get_public_config(),
        "automation": odoo_automation_worker.get_status(),
    }


@router.post("/session/test")
async def test_connection() -> Dict[str, Any]:
    try:
        result = await asyncio.to_thread(odoo_integration.test_connection)
        odoo_integration.save_config({"last_error": ""})
        return result
    except Exception as exc:
        message = _friendly_error(exc)
        odoo_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/orders/find")
async def find_order(request: OdooSearchOrderRequest) -> Dict[str, Any]:
    try:
        order = await asyncio.to_thread(odoo_integration.find_sale_order_by_envio, request.envio_id)
        return {
            "envio_id": request.envio_id,
            "found": bool(order),
            "order": order,
        }
    except Exception as exc:
        message = _friendly_error(exc)
        odoo_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/invoices/pending")
async def search_pending_invoices(request: OdooSearchInvoicesRequest) -> Dict[str, Any]:
    try:
        invoices = await asyncio.to_thread(
            odoo_integration.find_invoiced_sales,
            request.date_from,
            request.date_to,
            request.limit,
            None,
            True,
        )
        return {
            "date_from": request.date_from,
            "date_to": request.date_to,
            "limit": request.limit,
            "items": invoices,
        }
    except Exception as exc:
        message = _friendly_error(exc)
        odoo_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.get("/journals")
async def get_payment_journals() -> Dict[str, Any]:
    try:
        journals = await asyncio.to_thread(odoo_integration.get_payment_journals)
        return {"items": journals}
    except Exception as exc:
        message = _friendly_error(exc)
        odoo_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/invoices/register-payment")
async def register_payment(request: OdooRegisterPaymentRequest) -> Dict[str, Any]:
    try:
        result = await asyncio.to_thread(
            odoo_integration.register_invoice_payment,
            request.invoice_id,
            request.amount,
            request.payment_date,
            request.journal_id,
            request.memo,
        )
        return result
    except Exception as exc:
        message = _friendly_error(exc)
        odoo_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/invoices/search")
async def search_invoices(request: OdooSearchInvoicesRequest) -> Dict[str, Any]:
    try:
        invoices = await asyncio.to_thread(
            odoo_integration.find_invoiced_sales,
            request.date_from,
            request.date_to,
            request.limit,
        )
        return {
            "date_from": request.date_from,
            "date_to": request.date_to,
            "limit": request.limit,
            "items": invoices,
        }
    except Exception as exc:
        message = _friendly_error(exc)
        odoo_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


def _normalize_m2o_field(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return str(value[1] if len(value) >= 2 else value[0] if value else "")
    return str(value)


@router.post("/invoices/export")
async def export_invoices(request: OdooSearchInvoicesRequest) -> StreamingResponse:
    try:
        invoices = await asyncio.to_thread(
            odoo_integration.find_invoiced_sales,
            request.date_from,
            request.date_to,
            request.limit,
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id",
            "name",
            "partner",
            "invoice_date",
            "currency",
            "amount_untaxed",
            "amount_total",
            "payment_state",
        ])

        totals_by_currency: Dict[str, Dict[str, float]] = {}

        def _safe_float(value: Any) -> float:
            try:
                return float(value)
            except Exception:
                return 0.0

        for invoice in invoices:
            currency = _normalize_m2o_field(invoice.get("currency_id"))
            amount_untaxed = _safe_float(invoice.get("amount_untaxed", 0))
            amount_total = _safe_float(invoice.get("amount_total", 0))

            writer.writerow([
                invoice.get("id", ""),
                invoice.get("name", ""),
                _normalize_m2o_field(invoice.get("partner_id")),
                invoice.get("invoice_date", ""),
                currency,
                f"{amount_untaxed:.2f}",
                f"{amount_total:.2f}",
                invoice.get("invoice_payment_state", ""),
            ])

            totals = totals_by_currency.setdefault(currency or "", {
                "count": 0,
                "untaxed": 0.0,
                "total": 0.0,
            })
            totals["count"] += 1
            totals["untaxed"] += amount_untaxed
            totals["total"] += amount_total

        if totals_by_currency:
            writer.writerow([])
            writer.writerow(["Totales por moneda"])
            writer.writerow(["currency", "count", "amount_untaxed", "amount_total"])
            for currency, totals in sorted(totals_by_currency.items()):
                writer.writerow([
                    currency,
                    totals["count"],
                    f"{totals['untaxed']:.2f}",
                    f"{totals['total']:.2f}",
                ])

        csv_bytes = output.getvalue().encode("utf-8-sig")
        output.close()

        date_from_part = request.date_from or "desde"
        date_to_part = request.date_to or "hasta"
        filename = f"facturas_{date_from_part}_{date_to_part}.csv"

        headers = {
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8",
        }
        return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv", headers=headers)
    except Exception as exc:
        message = _friendly_error(exc)
        odoo_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/orders/print")
async def print_order(request: OdooPrintOrderRequest) -> Dict[str, Any]:
    try:
        order = await asyncio.to_thread(odoo_integration.find_sale_order_by_envio, request.envio_id)
        if not order:
            raise HTTPException(status_code=404, detail=f"No se encontro orden Odoo para envio {request.envio_id}")
        pdf_bytes = await asyncio.to_thread(
            odoo_integration.download_sale_order_report_pdf,
            int(order["id"]),
            str(odoo_integration.config.get("report_name", "")),
        )
        result = await asyncio.to_thread(
            odoo_integration.print_order_pdf,
            pdf_bytes,
            request.envio_id,
            request.printer,
            request.copies,
        )
        return {
            "envio_id": request.envio_id,
            "order": order,
            "print_result": result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        message = _friendly_error(exc)
        odoo_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.get("/automation/status")
async def get_automation_status() -> Dict[str, Any]:
    return odoo_automation_worker.get_status()


@router.post("/automation/run-once")
async def run_automation_once() -> Dict[str, Any]:
    try:
        result = await asyncio.to_thread(odoo_automation_worker.run_once)
        return result
    except Exception as exc:
        message = _friendly_error(exc)
        odoo_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/automation/reset-processed")
async def reset_automation_processed() -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(odoo_automation_worker.reset_processed)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/operator-users")
async def get_operator_users() -> Dict[str, Any]:
    return {"items": odoo_integration.get_operator_odoo_users_public()}


@router.post("/operator-users")
async def upsert_operator_user(request: OdooOperatorUserRequest) -> Dict[str, Any]:
    try:
        items = await asyncio.to_thread(
            odoo_integration.set_operator_odoo_user,
            request.app_username,
            request.odoo_username,
            request.odoo_password,
        )
        return {"items": items}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/operator-users/{app_username}")
async def delete_operator_user(app_username: str) -> Dict[str, Any]:
    try:
        items = await asyncio.to_thread(
            odoo_integration.delete_operator_odoo_user,
            app_username,
        )
        return {"items": items}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
