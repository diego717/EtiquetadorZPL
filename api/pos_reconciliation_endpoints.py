"""
Endpoints de conciliacion de pagos POS: cruza cupones de TotalNet contra
facturas pendientes en Odoo y, tras confirmacion del operador, registra el
pago en Odoo. Nunca escribe nada sin un paso de confirmacion explicito.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from odoo_integration import odoo_integration
from totalnet_integration import totalnet_integration
import pos_reconciliation as recon
from totalnet_receipt_pdf import (
    build_totalnet_receipt_filename,
    generate_totalnet_transaction_pdf,
)

router = APIRouter(prefix="/api/pos-reconciliation", tags=["pos-reconciliation"])


def _friendly_error(exc: Exception) -> str:
    message = str(exc or "").strip()
    return message or "Error inesperado en conciliacion de pagos POS"


class PosReconciliationSyncRequest(BaseModel):
    date_from: str
    date_to: str


class ManualPosTicketRequest(BaseModel):
    transaction_date: str
    invoice_number: str
    amount: float
    currency: str = "UYU"
    ticket: str
    authorization: str
    brand: str
    product: str = "DEBITO"
    batch: str = ""
    terminal: str = ""
    last_four: str = ""


class ConfirmItem(BaseModel):
    cupon: Dict[str, Any]
    invoice_id: int
    invoice_name: str = ""
    journal_id: Optional[int] = None
    round_to_integer: bool = False
    rounding_account_id: Optional[int] = None
    attach_receipt_pdf: bool = True
    memo: str = ""


class PosReconciliationConfirmRequest(BaseModel):
    operator_app_username: str
    items: List[ConfirmItem]


class PosReconciliationConfigRequest(BaseModel):
    amount_tolerance: Optional[float] = None
    date_window_days: Optional[int] = None
    journal_map: Optional[Dict[str, Any]] = None


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return await asyncio.to_thread(recon.load_recon_config)


@router.post("/config")
async def save_config(request: PosReconciliationConfigRequest) -> Dict[str, Any]:
    updates = {k: v for k, v in request.dict().items() if v is not None}
    return await asyncio.to_thread(recon.save_recon_config, updates)


@router.get("/journals")
async def get_journals() -> Dict[str, Any]:
    try:
        journals = await asyncio.to_thread(odoo_integration.get_payment_journals)
        return {"items": journals}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_friendly_error(exc))


@router.get("/rounding-accounts")
async def get_rounding_accounts() -> Dict[str, Any]:
    try:
        accounts = await asyncio.to_thread(odoo_integration.get_rounding_accounts)
        return {"items": accounts}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_friendly_error(exc))


@router.get("/operators")
async def get_payment_operators() -> Dict[str, Any]:
    """Lista operadores seleccionables sin exponer sus contrasenas Odoo."""
    return {
        "selection_required": True,
        "items": odoo_integration.get_operator_odoo_users_public(),
    }


@router.post("/sync")
async def sync(request: PosReconciliationSyncRequest) -> Dict[str, Any]:
    if not totalnet_integration.is_configured():
        raise HTTPException(status_code=400, detail="TotalNet no esta configurado (falta client_id/secret/token_url)")
    if not odoo_integration.is_configured():
        raise HTTPException(status_code=400, detail="Odoo no esta configurado")

    try:
        recon_config = await asyncio.to_thread(recon.load_recon_config)
        lookahead_days = int(
            recon_config.get("settlement_lookahead_days", recon.DEFAULT_SETTLEMENT_LOOKAHEAD_DAYS)
        )
        settlement_from, settlement_to = recon.resolve_settlement_query_range(
            request.date_from, request.date_to, lookahead_days
        )
        cupones = await asyncio.to_thread(
            totalnet_integration.get_all_cupones, settlement_from, settlement_to
        )
        cupones = recon.filter_cupones_by_transaction_date(cupones, request.date_from, request.date_to)
        invoices = await asyncio.to_thread(
            odoo_integration.find_invoiced_sales,
            date_from=request.date_from,
            date_to=request.date_to,
            only_cash_payment_term=True,
        )
        processed_ids = await asyncio.to_thread(recon.load_processed_cupon_ids)

        result = recon.match_cupones_to_invoices(
            cupones,
            invoices,
            amount_tolerance=float(recon_config.get("amount_tolerance", recon.DEFAULT_AMOUNT_TOLERANCE)),
            date_window_days=int(recon_config.get("date_window_days", recon.DEFAULT_DATE_WINDOW_DAYS)),
            exclude_cupon_ids=processed_ids,
        )

        journal_map = recon_config.get("journal_map", {}) or {}
        for match in result["matches_unicos"]:
            match["suggested_journal_id"] = recon.resolve_journal_id(match["cupon"].get("sello"), journal_map)
            match["suggested_memo"] = recon.build_payment_memo(match["invoice"].get("name"), match["cupon"])

        return {
            "matching_version": 4,
            "date_from": request.date_from,
            "date_to": request.date_to,
            "settlement_date_from": settlement_from,
            "settlement_date_to": settlement_to,
            "total_cupones": len(cupones),
            "total_facturas_contado": len(invoices),
            "total_facturas_pendientes_contado": sum(
                str(invoice.get("invoice_payment_state") or "") in {"not_paid", "partial"}
                for invoice in invoices
            ),
            **result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_friendly_error(exc))


@router.post("/pending-invoices")
async def pending_invoices(request: PosReconciliationSyncRequest) -> Dict[str, Any]:
    """Lista contado pendiente desde Odoo sin depender de la API de TotalNet."""
    if not odoo_integration.is_configured():
        raise HTTPException(status_code=400, detail="Odoo no esta configurado")
    try:
        invoices = await asyncio.to_thread(
            odoo_integration.find_invoiced_sales,
            date_from=request.date_from,
            date_to=request.date_to,
            only_pending=True,
            only_cash_payment_term=True,
        )
        items = []
        for invoice in invoices:
            summary = recon._invoice_summary(invoice)
            summary["invoice_origin"] = invoice.get("invoice_origin") or ""
            summary["rounded_amount"] = recon.round_payment_amount(
                invoice.get("amount_residual")
                if invoice.get("amount_residual") is not None
                else invoice.get("amount_total")
            )
            items.append(summary)
        return {
            "date_from": request.date_from,
            "date_to": request.date_to,
            "total": len(items),
            "items": items,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_friendly_error(exc))


@router.post("/manual-match")
async def manual_match(request: ManualPosTicketRequest) -> Dict[str, Any]:
    """Busca en Odoo un comprobante fisico que TotalNet aun no expone por API.

    Este endpoint solo propone la coincidencia. El pago conserva el mismo paso
    posterior de seleccion y confirmacion explicita que los cupones automaticos.
    """
    if not odoo_integration.is_configured():
        raise HTTPException(status_code=400, detail="Odoo no esta configurado")

    try:
        transaction_date = date.fromisoformat(str(request.transaction_date or "").strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="La fecha del ticket debe usar formato YYYY-MM-DD") from exc
    if transaction_date > date.today():
        raise HTTPException(status_code=400, detail="La fecha del ticket no puede ser futura")

    invoice_number = recon._invoice_number(request.invoice_number)
    if not invoice_number:
        raise HTTPException(status_code=400, detail="Ingresa el numero de factura impreso en el ticket")
    ticket = str(request.ticket or "").strip()
    authorization = str(request.authorization or "").strip()
    brand = str(request.brand or "").strip().upper()
    currency = str(request.currency or "UYU").strip().upper()
    product = str(request.product or "DEBITO").strip().upper()
    if not ticket or not authorization or not brand:
        raise HTTPException(
            status_code=400,
            detail="Ticket, autorizacion y sello son obligatorios",
        )
    if currency not in {"UYU", "USD"}:
        raise HTTPException(status_code=400, detail="La moneda debe ser UYU o USD")
    try:
        amount = Decimal(str(request.amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="El importe del ticket no es valido") from exc
    if amount <= 0:
        raise HTTPException(status_code=400, detail="El importe del ticket debe ser mayor a cero")

    fingerprint_source = "|".join(
        (
            transaction_date.isoformat(),
            invoice_number,
            f"{amount:.2f}",
            currency,
            ticket.lower(),
            authorization.lower(),
            brand.lower(),
        )
    )
    coupon_id = "manual-" + hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:24]
    processed_ids = await asyncio.to_thread(recon.load_processed_cupon_ids)
    if coupon_id in processed_ids:
        raise HTTPException(
            status_code=409,
            detail="Este ticket manual ya fue confirmado anteriormente",
        )

    coupon = {
        "transaccion": {
            "cupon_id": coupon_id,
            "ticket": ticket,
            "autorizacion": authorization,
            "lote": str(request.batch or "").strip(),
            "numero_factura": invoice_number,
            "importe": float(amount),
            "moneda": currency,
            "fecha_cupon": transaction_date.isoformat(),
            "sello": brand,
            "producto": product,
            "terminal": str(request.terminal or "").strip(),
            "ultimos_4_Digitos": str(request.last_four or "").strip()[-4:],
            "origen": "ticket_manual",
        },
        "liquidacion": {},
    }

    try:
        recon_config = await asyncio.to_thread(recon.load_recon_config)
        date_window_days = max(
            0,
            min(15, int(recon_config.get("date_window_days", recon.DEFAULT_DATE_WINDOW_DAYS))),
        )
        search_from = (transaction_date - timedelta(days=date_window_days)).isoformat()
        search_to = (transaction_date + timedelta(days=date_window_days)).isoformat()
        invoices = await asyncio.to_thread(
            odoo_integration.find_invoiced_sales,
            date_from=search_from,
            date_to=search_to,
            only_cash_payment_term=True,
        )
        result = recon.match_cupones_to_invoices(
            [coupon],
            invoices,
            amount_tolerance=float(
                recon_config.get("amount_tolerance", recon.DEFAULT_AMOUNT_TOLERANCE)
            ),
            date_window_days=date_window_days,
            exclude_cupon_ids=processed_ids,
        )
        journal_map = recon_config.get("journal_map", {}) or {}
        for match in result["matches_unicos"]:
            match["suggested_journal_id"] = recon.resolve_journal_id(
                match["cupon"].get("sello"), journal_map
            )
            match["suggested_memo"] = recon.build_payment_memo(
                match["invoice"].get("name"), match["cupon"]
            )
        return {
            "matching_version": 4,
            "source": "manual_ticket",
            "date_from": search_from,
            "date_to": search_to,
            "total_cupones": 1,
            "total_facturas_contado": len(invoices),
            "total_facturas_pendientes_contado": sum(
                str(invoice.get("invoice_payment_state") or "") in {"not_paid", "partial"}
                for invoice in invoices
            ),
            **result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_friendly_error(exc))


@router.post("/confirm")
async def confirm(request: PosReconciliationConfirmRequest) -> Dict[str, Any]:
    if not request.items:
        raise HTTPException(status_code=400, detail="No hay items para confirmar")

    operator_app_username = str(request.operator_app_username or "").strip().lower()
    if not operator_app_username:
        raise HTTPException(status_code=400, detail="Selecciona el usuario que registrara el pago en Odoo")
    auth_override = odoo_integration.resolve_operator_auth_exact(operator_app_username)
    if not auth_override:
        raise HTTPException(
            status_code=400,
            detail=f"El operador '{operator_app_username}' no tiene credenciales Odoo completas",
        )
    actor_odoo_username = str(auth_override.get("username") or "").strip()
    try:
        # Validar las credenciales antes de iniciar una confirmacion de varios pagos.
        await asyncio.to_thread(odoo_integration._authenticate, auth_override)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo autenticar en Odoo como {actor_odoo_username}: {_friendly_error(exc)}",
        )

    results: List[Dict[str, Any]] = []
    processed_cupon_ids: List[Any] = []
    recon_config = await asyncio.to_thread(recon.load_recon_config)

    for item in request.items:
        cupon = item.cupon
        journal_id = item.journal_id
        if journal_id is None:
            journal_id = recon.resolve_journal_id(cupon.get("sello"), recon_config.get("journal_map", {}) or {})

        entry: Dict[str, Any] = {
            "cupon_id": cupon.get("cupon_id"),
            "invoice_id": item.invoice_id,
            "operator_app_username": operator_app_username,
            "actor_odoo_username": actor_odoo_username,
        }
        if not journal_id:
            entry["ok"] = False
            sello = str(cupon.get("sello") or "sin sello")
            entry["error"] = (
                f"No hay diario contable asignado para {sello}. "
                "Selecciona un diario al confirmar o configura el mapeo por sello."
            )
            results.append(entry)
            continue

        memo = item.memo or recon.build_payment_memo(item.invoice_name, cupon)
        try:
            payment_date = recon.normalize_date_iso(cupon.get("fecha"))
            original_amount = float(cupon.get("importe") or 0)
            payment_amount = (
                recon.round_payment_amount(original_amount)
                if item.round_to_integer
                else original_amount
            )
            payment_result = await asyncio.to_thread(
                odoo_integration.register_invoice_payment,
                item.invoice_id,
                payment_amount,
                payment_date,
                int(journal_id),
                memo,
                auth_override,
                True,
                item.rounding_account_id if item.round_to_integer else None,
                original_amount if item.round_to_integer else None,
            )
            entry["ok"] = True
            entry["result"] = payment_result
            entry["original_amount"] = original_amount
            entry["payment_amount"] = payment_amount
            entry["rounding_difference"] = round(payment_amount - original_amount, 2)
            if item.attach_receipt_pdf:
                payment_id = payment_result.get("payment_id")
                if not payment_id:
                    # El pago ya fue creado. Informar la advertencia sin marcarlo
                    # como fallido para evitar que un reintento duplique el cobro.
                    entry["attachment_ok"] = False
                    entry["warning"] = (
                        "El pago se registro, pero no se pudo ubicar el pago creado en Odoo "
                        "para adjuntar el PDF TotalNet."
                    )
                else:
                    try:
                        filename = build_totalnet_receipt_filename(cupon)
                        pdf_bytes = generate_totalnet_transaction_pdf(cupon)
                        attachment_result = await asyncio.to_thread(
                            odoo_integration.attach_totalnet_receipt_to_payment,
                            payment_id,
                            filename,
                            pdf_bytes,
                            auth_override,
                        )
                        entry["attachment_ok"] = True
                        entry["attachment"] = attachment_result
                    except Exception as attachment_exc:
                        entry["attachment_ok"] = False
                        entry["warning"] = (
                            "El pago se registro, pero no se pudo adjuntar el PDF TotalNet: "
                            f"{_friendly_error(attachment_exc)}"
                        )
            if cupon.get("cupon_id") is not None:
                processed_cupon_ids.append(cupon.get("cupon_id"))
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = _friendly_error(exc)

        results.append(entry)

    if processed_cupon_ids:
        await asyncio.to_thread(recon.mark_cupones_processed, processed_cupon_ids, results)

    return {
        "operator": {
            "app_username": operator_app_username,
            "odoo_username": actor_odoo_username,
        },
        "items": results,
    }


@router.get("/history")
async def get_history() -> Dict[str, Any]:
    return await asyncio.to_thread(recon.load_state)
