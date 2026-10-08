"""
Endpoints de conciliacion de pagos POS: cruza cupones de TotalNet contra
facturas pendientes en Odoo y, tras confirmacion del operador, registra el
pago en Odoo. Nunca escribe nada sin un paso de confirmacion explicito.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from odoo_integration import odoo_integration
from totalnet_integration import totalnet_integration
import pos_reconciliation as recon
import pos_reconciliation_service as service
from pos_reconciliation_worker import pos_reconciliation_worker

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
    auto_sync_enabled: Optional[bool] = None
    auto_sync_interval_minutes: Optional[int] = None
    auto_sync_lookback_days: Optional[int] = None
    auto_sync_notify_desktop: Optional[bool] = None
    auto_register_deterministic: Optional[bool] = None
    auto_register_operator: Optional[str] = None


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return await asyncio.to_thread(recon.load_recon_config)


@router.post("/config")
async def save_config(request: PosReconciliationConfigRequest) -> Dict[str, Any]:
    updates = {k: v for k, v in request.dict().items() if v is not None}
    if "auto_register_operator" in updates:
        updates["auto_register_operator"] = str(updates["auto_register_operator"]).strip().lower()
    enabling_auto_register = updates.get("auto_register_deterministic") is True
    operator = updates.get(
        "auto_register_operator",
        (await asyncio.to_thread(recon.load_recon_config)).get("auto_register_operator", ""),
    )
    if enabling_auto_register and not odoo_integration.resolve_operator_auth_exact(operator):
        raise HTTPException(
            status_code=400,
            detail="Para registrar pagos automaticamente elige un operador con credenciales Odoo completas",
        )
    return await asyncio.to_thread(recon.save_recon_config, updates)


@router.get("/auto/status")
async def get_auto_status() -> Dict[str, Any]:
    return await asyncio.to_thread(pos_reconciliation_worker.get_status)


@router.get("/auto/proposal")
async def get_auto_proposal() -> Dict[str, Any]:
    proposal = await asyncio.to_thread(pos_reconciliation_worker.get_last_proposal)
    if not proposal:
        raise HTTPException(status_code=404, detail="Todavia no hay una sincronizacion automatica")
    return proposal


@router.post("/auto/run-once")
async def run_auto_once() -> Dict[str, Any]:
    result = await asyncio.to_thread(pos_reconciliation_worker.run_cycle, True)
    if not result.get("ok") and result.get("reason") != "cycle_in_progress":
        raise HTTPException(status_code=400, detail=result.get("error") or "Fallo la sincronizacion")
    return result


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
        return await asyncio.to_thread(
            service.build_sync_proposal,
            totalnet_integration,
            odoo_integration,
            request.date_from,
            request.date_to,
        )
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
            "matching_version": service.MATCHING_VERSION,
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
            "cupon": dict(cupon),
            "invoice_id": item.invoice_id,
            "invoice_name": item.invoice_name,
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

        try:
            entry.update(
                await asyncio.to_thread(
                    service.register_confirmed_payment,
                    odoo_integration,
                    cupon,
                    item.invoice_id,
                    item.invoice_name,
                    int(journal_id),
                    item.memo,
                    auth_override,
                    item.round_to_integer,
                    item.rounding_account_id,
                    item.attach_receipt_pdf,
                )
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
    state = await asyncio.to_thread(recon.load_state)
    items: List[Dict[str, Any]] = []
    for batch in reversed(state.get("history", []) or []):
        registered_at = batch.get("at")
        for payment in reversed(batch.get("payments", []) or []):
            item = dict(payment)
            payment_result = item.get("result") if isinstance(item.get("result"), dict) else {}
            invoice_id = item.get("invoice_id") or payment_result.get("invoice_id")
            payment_id = item.get("payment_id") or payment_result.get("payment_id")
            action_result = payment_result.get("action_result")
            if (
                not payment_id
                and isinstance(action_result, dict)
                and action_result.get("res_model") == "account.payment"
            ):
                payment_id = action_result.get("res_id")

            # Las primeras versiones no guardaban los datos visibles del cupon.
            # Recuperar numero de factura y ticket desde el nombre del PDF cuando
            # este disponible permite que el historial previo siga siendo util.
            coupon = item.get("cupon") if isinstance(item.get("cupon"), dict) else {}
            attachment = item.get("attachment") if isinstance(item.get("attachment"), dict) else {}
            filename = str(attachment.get("filename") or "")
            if filename and not coupon:
                invoice_match = re.search(r"_Fact_([^_]+)", filename, flags=re.IGNORECASE)
                ticket_match = re.search(r"_Ticket_([^_]+)", filename, flags=re.IGNORECASE)
                coupon = {
                    "ticket": ticket_match.group(1) if ticket_match else "",
                    "importe": item.get("original_amount"),
                    "numero_factura": invoice_match.group(1) if invoice_match else "",
                }
                item["cupon"] = coupon
            if not item.get("invoice_name") and coupon.get("numero_factura"):
                item["invoice_name"] = f"Factura {coupon['numero_factura']}"
            item["registered_at"] = registered_at
            item["invoice_id"] = invoice_id
            item["payment_id"] = payment_id
            item["invoice_url"] = ""
            item["payment_url"] = ""
            try:
                if invoice_id:
                    item["invoice_url"] = odoo_integration.record_url("account.move", invoice_id)
                if payment_id:
                    item["payment_url"] = odoo_integration.record_url("account.payment", payment_id)
            except Exception:
                # El historial debe seguir siendo consultable aunque la URL base
                # de Odoo este temporalmente incompleta o invalida.
                pass
            items.append(item)
    return {
        "processed_cupon_ids": state.get("processed_cupon_ids", []),
        "history": state.get("history", []),
        "total": len(items),
        "items": items,
    }
