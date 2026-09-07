"""Generacion del comprobante PDF a partir de datos estructurados de TotalNet."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Iterable, Tuple

import fitz


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


def _date_display(value: Any) -> str:
    return _text(value).replace("/", "-")


def _rows(coupon: Dict[str, Any]) -> Iterable[Tuple[str, str]]:
    payment_form = " - ".join(
        value
        for value in (
            _text(coupon.get("forma_pago"), ""),
            _text(coupon.get("banco_acreditacion"), ""),
        )
        if value
    ) or "-"
    last_four = _text(coupon.get("ultimos_4_digitos"), "")
    return (
        ("Tipo de producto", _text(coupon.get("producto"))),
        ("Moneda", _text(coupon.get("moneda"))),
        ("Importe", _money(coupon.get("importe"))),
        ("Propina", _money(coupon.get("propina") or 0)),
        ("Cuotas", _text(coupon.get("cuotas"))),
        ("Sello", _text(coupon.get("sello"))),
        ("BIN", _text(coupon.get("bin"))),
        ("Últimos 4 dígitos", last_four or "-"),
        ("Nro. de factura", _text(coupon.get("numero_factura"))),
        ("Ticket", _text(coupon.get("ticket"))),
        ("Autorización", _text(coupon.get("autorizacion"))),
        ("Lote", _text(coupon.get("lote"))),
        ("Terminal", _text(coupon.get("terminal"))),
        ("Fecha de liquidación", _date_display(coupon.get("fecha_liquidacion"))),
        ("Devolución de impuesto", _money(coupon.get("importe_devolucion_impuesto") or 0)),
        ("Código devolución impuesto", _text(coupon.get("devolucion_impuesto"))),
        ("Total cobrado", _money(coupon.get("total_pagado"))),
        ("Forma de pago", payment_form),
        ("Fecha de pago", _date_display(coupon.get("fecha_pago"))),
    )


def build_totalnet_receipt_filename(coupon: Dict[str, Any]) -> str:
    invoice = _text(coupon.get("numero_factura"), "sin_factura")
    ticket = _text(coupon.get("ticket"), "sin_ticket")
    coupon_id = _text(coupon.get("cupon_id"), "sin_id")
    safe = lambda value: "".join(char for char in value if char.isalnum() or char in "-_")
    return f"TotalNet_Fact_{safe(invoice)}_Ticket_{safe(ticket)}_Cupon_{safe(coupon_id)}.pdf"


def generate_totalnet_transaction_pdf(coupon: Dict[str, Any]) -> bytes:
    """Crea un PDF A4 legible sin depender de una captura o portal web."""
    document = fitz.open()
    try:
        page = document.new_page(width=595, height=842)
        page.draw_rect(page.rect, color=(0.86, 0.88, 0.91), fill=(1, 1, 1), width=0.8)
        title = "Detalle de la transacción"
        title_width = fitz.get_text_length(title, fontname="helv", fontsize=17)
        page.insert_text(
            ((595 - title_width) / 2, 50),
            title,
            fontname="helv",
            fontsize=17,
            color=(0.10, 0.13, 0.18),
        )
        subtitle = (
            "Comprobante transcripto manualmente desde el ticket TotalNet"
            if coupon.get("manual_entry")
            else "Comprobante generado desde la API de TotalNet"
        )
        subtitle_width = fitz.get_text_length(subtitle, fontname="helv", fontsize=9)
        page.insert_text(
            ((595 - subtitle_width) / 2, 72),
            subtitle,
            fontname="helv",
            fontsize=9,
            color=(0.36, 0.40, 0.46),
        )
        y = 92.0
        row_height = 33.0
        for label, value in _rows(coupon):
            page.draw_line((44, y + row_height - 5), (551, y + row_height - 5), color=(0.84, 0.86, 0.89), width=0.6)
            page.insert_textbox(
                fitz.Rect(48, y, 235, y + row_height - 7),
                f"{label}:",
                fontname="hebo",
                fontsize=10.2,
                color=(0.13, 0.16, 0.21),
            )
            page.insert_textbox(
                fitz.Rect(235, y, 547, y + row_height - 7),
                value,
                fontname="helv",
                fontsize=10.2,
                color=(0.25, 0.29, 0.35),
            )
            y += row_height

        marker = f"Cupon TotalNet: {_text(coupon.get('cupon_id'))}"
        page.insert_textbox(
            fitz.Rect(44, 775, 551, 808),
            marker,
            fontname="helv",
            fontsize=8,
            align=fitz.TEXT_ALIGN_CENTER,
            color=(0.48, 0.51, 0.56),
        )
        document.set_metadata(
            {
                "title": f"Detalle TotalNet - Factura {_text(coupon.get('numero_factura'))}",
            "subject": marker,
                "creator": "EtiquetadorZPL",
            }
        )
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()
