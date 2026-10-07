"""
Operaciones de conciliacion POS compartidas entre los endpoints (operador) y
el worker en segundo plano. Las integraciones se reciben por parametro para
que cada llamador use su propia instancia (y los tests puedan reemplazarlas).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

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
