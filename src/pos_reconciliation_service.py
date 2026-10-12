"""
Operaciones de conciliacion POS compartidas entre los endpoints (operador) y
el worker en segundo plano. Las integraciones se reciben por parametro para
que cada llamador use su propia instancia (y los tests puedan reemplazarlas).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional

import pos_reconciliation as recon
from company_branding import get_branding
from totalnet_receipt_pdf import (
    build_totalnet_receipt_filename,
    generate_totalnet_transaction_pdf,
)

MATCHING_VERSION = 4


def build_sync_proposal(totalnet: Any, odoo: Any, date_from: str, date_to: str) -> Dict[str, Any]:
    """Trae cupones y facturas y arma la propuesta de conciliacion. No escribe en Odoo."""
    recon_config = recon.load_recon_config()
    lookahead_days = int(
        recon_config.get("settlement_lookahead_days", recon.DEFAULT_SETTLEMENT_LOOKAHEAD_DAYS)
    )
    settlement_from, settlement_to = recon.resolve_settlement_query_range(
        date_from, date_to, lookahead_days
    )
    cupones = totalnet.get_all_cupones(settlement_from, settlement_to)
    cupones = recon.filter_cupones_by_transaction_date(cupones, date_from, date_to)
    invoices = odoo.find_invoiced_sales(
        date_from=date_from,
        date_to=date_to,
        only_cash_payment_term=True,
    )
    processed_ids = recon.load_processed_cupon_ids()

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
        "matching_version": MATCHING_VERSION,
        "date_from": date_from,
        "date_to": date_to,
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


def register_confirmed_payment(
    odoo: Any,
    cupon: Dict[str, Any],
    invoice_id: int,
    invoice_name: str,
    journal_id: int,
    memo: str,
    auth_override: Optional[Dict[str, str]],
    round_to_integer: bool = False,
    rounding_account_id: Optional[int] = None,
    attach_receipt_pdf: bool = True,
) -> Dict[str, Any]:
    """Registra un pago ya confirmado (por operador o por regla deterministica).

    Lanza excepcion si el pago no se pudo crear. Si el pago se creo pero el
    adjunto fallo, devuelve una advertencia sin marcarlo como fallido: un
    reintento duplicaria el cobro.
    """
    memo = memo or recon.build_payment_memo(invoice_name, cupon)
    payment_date = recon.normalize_date_iso(cupon.get("fecha"))
    original_amount = float(cupon.get("importe") or 0)
    payment_amount = (
        recon.round_payment_amount(original_amount) if round_to_integer else original_amount
    )
    payment_result = odoo.register_invoice_payment(
        invoice_id,
        payment_amount,
        payment_date,
        int(journal_id),
        memo,
        auth_override,
        True,
        rounding_account_id if round_to_integer else None,
        original_amount if round_to_integer else None,
    )
    entry: Dict[str, Any] = {
        "ok": True,
        "result": payment_result,
        "original_amount": original_amount,
        "payment_amount": payment_amount,
        "rounding_difference": round(payment_amount - original_amount, 2),
    }
    if not attach_receipt_pdf:
        return entry

    payment_id = payment_result.get("payment_id")
    if not payment_id:
        entry["attachment_ok"] = False
        entry["warning"] = (
            "El pago se registro, pero no se pudo ubicar el pago creado en Odoo "
            "para adjuntar el PDF TotalNet."
        )
        return entry
    try:
        filename = build_totalnet_receipt_filename(cupon)
        pdf_bytes = generate_totalnet_transaction_pdf(cupon, get_branding(odoo))
        entry["attachment"] = odoo.attach_totalnet_receipt_to_payment(
            payment_id,
            filename,
            pdf_bytes,
            auth_override,
        )
        entry["attachment_ok"] = True
    except Exception as attachment_exc:
        message = str(attachment_exc or "").strip() or "error desconocido"
        entry["attachment_ok"] = False
        entry["warning"] = f"El pago se registro, pero no se pudo adjuntar el PDF TotalNet: {message}"
    return entry


# ---- Transferencias bancarias ----

TRANSFER_MAX_WRITEOFF_RATIO = 0.05
TRANSFER_ATTACHMENT_TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
TRANSFER_ATTACHMENT_MAX_BYTES = 8 * 1024 * 1024

# Cobros manuales que comparten el flujo de transferencia (factura elegida a mano).
# - mercadopago: el numero de autorizacion va solo en el memo; sin comprobante.
# - caja: efectivo en un diario de caja; sin referencia, memo ni comprobante.
MANUAL_PAYMENT_METHODS: Dict[str, Dict[str, Any]] = {
    "transferencia": {
        "label": "transferencia",
        "journal_type": "bank",
        "journal_label": "un diario de banco",
        "reference_required": "Falta la referencia o numero de la transferencia",
        "allows_attachment": True,
    },
    "mercadopago": {
        "label": "Mercado Pago",
        "journal_type": "bank",
        "journal_label": "un diario de banco (Mercado Pago)",
        "reference_required": "Falta el numero de autorizacion de Mercado Pago",
        "allows_attachment": False,
    },
    "caja": {
        "label": "caja",
        "journal_type": "cash",
        "journal_label": "un diario de caja",
        "reference_required": "",
        "allows_attachment": False,
    },
}


def normalize_transfer_reference(value: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(value or "").upper())


def find_registered_transfer(
    reference: str,
    journal_id: int,
    history: List[Dict[str, Any]],
    source: str = "transferencia",
) -> Optional[Dict[str, Any]]:
    """Cobro manual ya registrado con la misma referencia en el mismo diario."""
    wanted = normalize_transfer_reference(reference)
    if not wanted:
        return None
    for batch in history or []:
        for payment in batch.get("payments", []) or []:
            transfer = payment.get("transfer") or {}
            if (
                payment.get("source") == source
                and payment.get("ok") is True
                and int(transfer.get("journal_id") or 0) == int(journal_id)
                and normalize_transfer_reference(transfer.get("reference")) == wanted
            ):
                return payment
    return None


def register_transfer_payment(
    odoo: Any,
    invoice_id: int,
    journal_id: int,
    amount: float,
    payment_date: str,
    reference: str,
    auth_override: Optional[Dict[str, str]],
    difference_handling: str = "open",
    difference_account_id: Optional[int] = None,
    attachment: Optional[Dict[str, Any]] = None,
    method: str = "transferencia",
) -> Dict[str, Any]:
    """Registra en Odoo el cobro de una factura recibido por transferencia, Mercado Pago o caja.

    Valida todo antes de escribir: moneda del banco igual a la de la factura, factura con
    saldo, referencia no usada y diferencia razonable si se da la factura por pagada.
    Como el resto de los cobros, si el pago se creo pero el adjunto fallo devuelve una
    advertencia y no un error: reintentar duplicaria el cobro.
    """
    method = str(method or "").strip().lower()
    config = MANUAL_PAYMENT_METHODS.get(method)
    if config is None:
        raise ValueError(f"Medio de cobro invalido: {method}")
    reference = str(reference or "").strip() if config["reference_required"] else ""
    if config["reference_required"] and not reference:
        raise ValueError(config["reference_required"])
    if attachment and not config["allows_attachment"]:
        raise ValueError(f"Los cobros por {config['label']} no llevan comprobante adjunto")
    try:
        amount_value = round(float(amount), 2)
    except (TypeError, ValueError):
        raise ValueError("Importe invalido")
    if amount_value <= 0:
        raise ValueError("El importe debe ser mayor a 0")
    payment_date = recon.normalize_date_iso(payment_date)
    if payment_date > date.today().isoformat():
        raise ValueError("La fecha del cobro no puede ser futura")
    if difference_handling not in {"open", "reconcile"}:
        raise ValueError("Opcion de diferencia invalida")

    previous = (
        find_registered_transfer(reference, journal_id, recon.load_state().get("history", []), method)
        if reference
        else None
    )
    if previous:
        what = "La transferencia" if method == "transferencia" else "La autorizacion de Mercado Pago"
        raise ValueError(
            f"{what} {reference} ya se registro en este diario "
            f"({previous.get('invoice_name') or 'factura ' + str(previous.get('invoice_id'))})."
        )

    context = odoo.get_invoice_payment_context(invoice_id, journal_id, auth_override)
    if context["move_type"] != "out_invoice" or context["state"] != "posted":
        raise ValueError(f"{context['invoice_name'] or 'El documento'} no es una factura de cliente publicada")
    if context["payment_state"] not in {"not_paid", "partial"}:
        raise ValueError(f"{context['invoice_name']} ya figura como pagada en Odoo")
    if context["journal_type"] != config["journal_type"]:
        raise ValueError(f"{context['journal_name']} no es {config['journal_label']}")
    if context["journal_currency"] != context["invoice_currency"]:
        raise ValueError(
            f"La factura esta en {context['invoice_currency']} y {context['journal_name']} "
            f"opera en {context['journal_currency']}. Elegi un diario en la misma moneda."
        )

    due = round(context["amount_residual"], 2)
    difference = round(due - amount_value, 2)
    writeoff_account = None
    if difference and difference_handling == "reconcile":
        if not difference_account_id:
            raise ValueError("Elegi la cuenta donde registrar la diferencia")
        limit = max(1.0, due * TRANSFER_MAX_WRITEOFF_RATIO)
        if abs(difference) > limit:
            raise ValueError(
                f"La diferencia ({difference:+.2f} {context['invoice_currency']}) supera el maximo para dar "
                f"la factura por pagada ({limit:.2f}). Registralo como pago parcial o revisa el importe."
            )
        writeoff_account = int(difference_account_id)

    if method == "transferencia":
        memo = f"Transferencia {reference} - {context['invoice_name']}"
    else:
        # Mercado Pago: solo el numero de autorizacion. Caja: sin memo.
        memo = reference
    payment_result = odoo.register_invoice_payment(
        int(invoice_id),
        amount_value,
        payment_date,
        int(journal_id),
        memo,
        auth_override,
        False,
        writeoff_account,
        None,
        # Centesimos: mismo concepto que el redondeo de los cobros POS.
        f"Redondeo cobro por {config['label']}" if abs(difference) < 1 else f"Diferencia cobro por {config['label']}",
    )
    entry: Dict[str, Any] = {
        "ok": True,
        "source": method,
        "invoice_id": int(invoice_id),
        "invoice_name": context["invoice_name"],
        "payment_id": payment_result.get("payment_id"),
        "result": payment_result,
        "transfer": {
            "reference": reference,
            "date": payment_date,
            "amount": amount_value,
            "currency": context["invoice_currency"],
            "journal_id": int(journal_id),
            "journal_name": context["journal_name"],
            "partner": context["partner"],
            "invoice_due": due,
            "difference": difference,
            "difference_handling": difference_handling if difference else "",
        },
    }

    if not attachment:
        return entry
    payment_id = payment_result.get("payment_id")
    if not payment_id:
        entry["attachment_ok"] = False
        entry["warning"] = "El pago se registro, pero no se pudo ubicar el pago en Odoo para adjuntar el comprobante."
        return entry
    try:
        extension = TRANSFER_ATTACHMENT_TYPES[attachment["mimetype"]]
        filename = f"Transferencia_{normalize_transfer_reference(reference)}_{context['invoice_name']}{extension}"
        filename = re.sub(r"[^\w.-]+", "_", filename)
        entry["attachment"] = odoo.attach_pdf_to_payment(
            payment_id, filename, attachment["content"], auth_override, attachment["mimetype"]
        )
        entry["attachment_ok"] = True
    except Exception as attachment_exc:
        message = str(attachment_exc or "").strip() or "error desconocido"
        entry["attachment_ok"] = False
        entry["warning"] = f"El pago se registro, pero no se pudo adjuntar el comprobante: {message}"
    return entry
