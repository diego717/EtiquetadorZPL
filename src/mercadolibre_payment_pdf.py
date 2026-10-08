"""Generacion del comprobante PDF para pagos de ventas de Mercado Libre."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import fitz

from company_branding import draw_footer, draw_header, hex_to_rgb, neutral_branding


TITLE = "Comprobante de pago Mercado Libre"
PAGE_WIDTH, PAGE_HEIGHT = 595, 842
MARGIN = 44
LABEL_X, VALUE_X, RIGHT_X = 52, 218, 547
FONT_SIZE = 9.5
ROW_PADDING = 6.0
MIN_ROW_HEIGHT = 26.0
CONTENT_BOTTOM = 760.0

ORDER_STATUS_LABELS = {
    "paid": "Pagada",
    "confirmed": "Confirmada",
    "payment_required": "Pago pendiente",
    "payment_in_process": "Pago en proceso",
    "partially_paid": "Pagada parcialmente",
    "partially_refunded": "Devuelta parcialmente",
    "pending_cancel": "Cancelación pendiente",
    "cancelled": "Cancelada",
    "invalid": "Inválida",
}

PAYMENT_STATUS_LABELS = {
    "approved": "Aprobado",
    "authorized": "Autorizado",
    "pending": "Pendiente",
    "in_process": "En proceso",
    "in_mediation": "En mediación",
    "rejected": "Rechazado",
    "cancelled": "Cancelado",
    "refunded": "Devuelto",
    "charged_back": "Contracargo",
}

PAYMENT_TYPE_LABELS = {
    "account_money": "Dinero en cuenta de Mercado Pago",
    "credit_card": "Tarjeta de crédito",
    "debit_card": "Tarjeta de débito",
    "prepaid_card": "Tarjeta prepaga",
    "ticket": "Efectivo en red de cobranza",
    "atm": "Cajero / red de cobranza",
    "bank_transfer": "Transferencia bancaria",
    "digital_currency": "Mercado Crédito",
    "digital_wallet": "Billetera digital",
    "voucher_card": "Tarjeta de beneficios",
    "crypto_transfer": "Criptomoneda",
}

PAYMENT_METHOD_LABELS = {
    "visa": "Visa",
    "debvisa": "Visa Débito",
    "master": "Mastercard",
    "debmaster": "Mastercard Débito",
    "amex": "American Express",
    "oca": "OCA",
    "creditel": "Creditel",
    "cabal": "Cabal",
    "diners": "Diners",
    "lider": "Líder",
    "abitab": "Abitab",
    "redpagos": "RedPagos",
    "consumer_credits": "Mercado Crédito",
}


def _text(value: Any, default: str = "-") -> str:
    result = str(value if value is not None else "").strip()
    return result or default


def _money(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value)
    formatted = f"{number:,.2f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _unique(values: List[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


def _translate(value: Any, labels: Dict[str, str]) -> str:
    text = _text(value, "")
    return labels.get(text.lower(), text.replace("_", " ").capitalize())


def _datetime_text(value: Any) -> str:
    text = _text(value, "")
    if not text:
        return "-"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text


def _payments(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [payment for payment in (order.get("payments") or []) if isinstance(payment, dict)]


def _payment_values(order: Dict[str, Any], key: str) -> List[str]:
    return [
        str(payment.get(key)).strip()
        for payment in _payments(order)
        if payment.get(key) not in (None, "")
    ]


def _payment_method_text(payment: Dict[str, Any]) -> str:
    """Tipo de pago en espanol, con la marca de la tarjeta cuando aporta."""
    payment_type = _text(payment.get("payment_type") or payment.get("payment_type_id"), "")
    method = _text(payment.get("payment_method_id"), "")
    type_label = _translate(payment_type, PAYMENT_TYPE_LABELS) if payment_type else ""
    if not method or method == payment_type:
        return type_label or "-"
    method_label = _translate(method, PAYMENT_METHOD_LABELS)
    if not type_label or method_label == type_label:
        return method_label
    return f"{type_label} {method_label}"


def _installments_text(order: Dict[str, Any]) -> str:
    counts = []
    for value in _payment_values(order, "installments"):
        try:
            counts.append(int(float(value)))
        except ValueError:
            continue
    multiple = _unique([f"{count} cuotas" for count in counts if count > 1])
    return ", ".join(multiple) or "Sin cuotas"


def _items_text(order: Dict[str, Any]) -> str:
    values = []
    for line in order.get("order_items") or []:
        item = line.get("item") or {}
        title = _text(item.get("title"), "Producto")
        quantity = line.get("quantity") or 1
        values.append(f"{quantity} x {title}")
    return "\n".join(values) or "-"


def _rows(order: Dict[str, Any], invoice_name: str = "") -> List[Tuple[str, str]]:
    buyer = order.get("buyer") or {}
    shipping = order.get("shipping") or {}
    payments = _payments(order)
    payment_ids = _unique(_payment_values(order, "id"))
    statuses = _unique([_translate(item.get("status"), PAYMENT_STATUS_LABELS) for item in payments])
    methods = _unique([_payment_method_text(item) for item in payments])
    order_ids = [str(value) for value in (order.get("order_ids") or []) if value]

    rows: List[Tuple[str, str]] = [
        ("Venta Mercado Libre" if order.get("pack_id") else "Orden Mercado Libre", _text(order.get("id"))),
    ]
    if order.get("pack_id"):
        rows.append(("Órdenes del pack", ", ".join(order_ids) or "-"))
    rows += [
        ("Factura Odoo", _text(invoice_name)),
        ("Estado de la venta", _translate(order.get("status"), ORDER_STATUS_LABELS) or "-"),
        ("Fecha de confirmación", _datetime_text(order.get("date_closed") or order.get("date_created"))),
        ("Comprador", _text(buyer.get("nickname") or buyer.get("id"))),
        ("Moneda", _text(order.get("currency_id"))),
    ]
    if order.get("shipping_amount") is not None:
        rows += [
            ("Total de productos", _money(order.get("total_amount"))),
            ("Envío pagado por el comprador", _money(order.get("shipping_amount"))),
        ]
    else:
        rows.append(("Total de la orden", _money(order.get("total_amount"))))
    rows += [
        ("Total pagado", _money(order.get("paid_amount") or order.get("total_amount"))),
        ("IDs de pago" if len(payment_ids) > 1 else "ID de pago", ", ".join(payment_ids) or "-"),
        ("Estado del pago", ", ".join(statuses) or "-"),
        ("Medio de pago", ", ".join(methods) or "-"),
        ("Cuotas", _installments_text(order)),
        ("Envío (shipment)", _text(shipping.get("id"))),
        ("Productos", _items_text(order)),
    ]
    return rows


def build_mercadolibre_payment_filename(order: Dict[str, Any]) -> str:
    order_id = _text(order.get("id"), "sin_orden")
    payment_ids = _payment_values(order, "id")
    payment_ref = "-".join(payment_ids) if payment_ids else "sin_pago"
    safe = lambda value: "".join(char for char in value if char.isalnum() or char in "-_")
    return f"MercadoLibre_Orden_{safe(order_id)}_Pago_{safe(payment_ref)}.pdf"


def _text_height(scratch: Any, text: str, width: float, fontname: str) -> float:
    """Alto que ocupa ``text`` envuelto en ``width``.

    insert_textbox no dibuja nada si el texto no entra, por eso se mide en una
    pagina descartable antes de reservar el alto de la fila.
    """
    height = FONT_SIZE * 1.6
    while height < PAGE_HEIGHT:
        spare = scratch.insert_textbox(
            fitz.Rect(0, 0, width, height), text, fontname=fontname, fontsize=FONT_SIZE
        )
        if spare >= 0:
            return height - spare
        height += FONT_SIZE
    return height


def generate_mercadolibre_payment_pdf(
    order: Dict[str, Any],
    invoice_name: str = "",
    branding: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Crea un PDF A4 usando los datos estructurados de la orden y sus pagos."""
    branding = branding or neutral_branding()
    label_color = hex_to_rgb(branding.get("table"))
    document = fitz.open()
    scratch_document = fitz.open()
    try:
        scratch = scratch_document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        y = draw_header(page, branding, TITLE, margin=MARGIN)
        for index, (label, value) in enumerate(_rows(order, invoice_name)):
            label_text = f"{label}:"
            content_height = max(
                _text_height(scratch, label_text, VALUE_X - LABEL_X, "hebo"),
                _text_height(scratch, value, RIGHT_X - VALUE_X, "helv"),
            )
            row_height = max(MIN_ROW_HEIGHT, content_height + 2 * ROW_PADDING)
            if y + row_height > CONTENT_BOTTOM:
                draw_footer(page, branding, TITLE, margin=MARGIN)
                page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
                y = float(MARGIN)
            if index % 2 == 0:
                page.draw_rect(
                    fitz.Rect(MARGIN, y, PAGE_WIDTH - MARGIN, y + row_height),
                    color=None,
                    fill=(0.965, 0.97, 0.975),
                )
            text_top = y + ROW_PADDING
            text_bottom = y + row_height - ROW_PADDING + 2
            page.insert_textbox(
                fitz.Rect(LABEL_X, text_top, VALUE_X, text_bottom),
                label_text,
                fontname="hebo",
                fontsize=FONT_SIZE,
                color=label_color,
            )
            page.insert_textbox(
                fitz.Rect(VALUE_X, text_top, RIGHT_X, text_bottom),
                value,
                fontname="helv",
                fontsize=FONT_SIZE,
                color=(0.2, 0.24, 0.3),
            )
            y += row_height

        marker_label = "Venta Mercado Libre" if order.get("pack_id") else "Orden Mercado Libre"
        marker = f"{marker_label}: {_text(order.get('id'))}"
        page.insert_textbox(
            fitz.Rect(MARGIN, 772, PAGE_WIDTH - MARGIN, 800),
            marker,
            fontname="helv",
            fontsize=8,
            align=fitz.TEXT_ALIGN_CENTER,
            color=(0.48, 0.51, 0.56),
        )
        draw_footer(page, branding, TITLE, margin=MARGIN)
        document.set_metadata(
            {
                "title": marker,
                "subject": f"Pago asociado a {invoice_name or 'factura Odoo'}",
                "author": branding.get("name") or "",
                "creator": "EtiquetadorZPL",
            }
        )
        return document.tobytes(garbage=4, deflate=True)
    finally:
        scratch_document.close()
        document.close()
