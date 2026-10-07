"""Generacion del comprobante PDF a partir de datos estructurados de TotalNet."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Iterable, Optional, Tuple

import fitz

from company_branding import draw_footer, draw_header, hex_to_rgb, neutral_branding


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


def generate_totalnet_transaction_pdf(coupon: Dict[str, Any], branding: Optional[Dict[str, Any]] = None) -> bytes:
    """Crea un PDF A4 legible sin depender de una captura o portal web."""
    branding = branding or neutral_branding()
    label_color = hex_to_rgb(branding.get("table"))
    document = fitz.open()
    try:
        page = document.new_page(width=595, height=842)
        subtitle = (
            "Comprobante transcripto manualmente desde el ticket TotalNet"
            if coupon.get("manual_entry")
            else "Comprobante generado desde la API de TotalNet"
        )
        y = draw_header(page, branding, "Detalle de la transacción", subtitle, margin=44)
        row_height = 28.0
        for index, (label, value) in enumerate(_rows(coupon)):
            if index % 2 == 0:
                page.draw_rect(fitz.Rect(44, y - 2, 551, y + row_height - 6), color=None, fill=(0.965, 0.97, 0.975))
            page.insert_textbox(
                fitz.Rect(52, y + 4, 235, y + row_height - 4),
                f"{label}:",
                fontname="hebo",
                fontsize=10,
                color=label_color,
            )
            page.insert_textbox(
                fitz.Rect(235, y + 4, 547, y + row_height - 4),
                value,
                fontname="helv",
                fontsize=10,
                color=(0.2, 0.24, 0.3),
            )
            y += row_height

        marker = f"Cupon TotalNet: {_text(coupon.get('cupon_id'))}"
        page.insert_textbox(
            fitz.Rect(44, 772, 551, 800),
            marker,
            fontname="helv",
            fontsize=8,
            align=fitz.TEXT_ALIGN_CENTER,
            color=(0.48, 0.51, 0.56),
        )
        draw_footer(page, branding, "Detalle de transacción TotalNet", margin=44)
        document.set_metadata(
            {
                "title": f"Detalle TotalNet - Factura {_text(coupon.get('numero_factura'))}",
                "subject": marker,
                "author": branding.get("name") or "",
                "creator": "EtiquetadorZPL",
            }
        )
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()
