"""
Estado de cuenta de un cliente en PDF A4 (facturas abiertas), generado con PyMuPDF.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

import fitz

from company_branding import neutral_branding, draw_footer, draw_header, hex_to_rgb
from receivables_monitor import format_money

PAGE_W, PAGE_H = 595, 842
MARGIN = 40
ROW_H = 18
# (titulo, ancho, alineacion derecha)
COLUMNS = [
    ("Comprobante", 150, False),
    ("Fecha", 62, False),
    ("Vencimiento", 70, False),
    ("Días venc.", 52, True),
    ("Total", 89, True),
    ("Saldo", 92, True),
]
TEXT = (0.1, 0.13, 0.17)
MUTED = (0.38, 0.42, 0.48)
LINE = (0.86, 0.88, 0.91)
WHITE = (1, 1, 1)


def _date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(value or "")


def _fit(text: str, width: float, size: float) -> str:
    if fitz.get_text_length(text, fontname="helv", fontsize=size) <= width:
        return text
    while text and fitz.get_text_length(text + "…", fontname="helv", fontsize=size) > width:
        text = text[:-1]
    return text + "…"


def _cell(page: Any, x: float, y: float, width: float, text: str, right: bool, size: float = 9, color=TEXT, bold=False) -> None:
    font = "hebo" if bold else "helv"
    text = _fit(text, width - 6, size)
    if right:
        x = x + width - 4 - fitz.get_text_length(text, fontname=font, fontsize=size)
    else:
        x = x + 3
    page.insert_text((x, y), text, fontname=font, fontsize=size, color=color)


def build_statement_filename(client: Dict[str, Any], as_of: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in str(client.get("name") or "cliente"))[:60].strip("_")
    return f"Estado_de_cuenta_{safe}_{as_of}.pdf"


def generate_statement_pdf(
    client: Dict[str, Any],
    invoices: List[Dict[str, Any]],
    company: str,
    as_of: str,
    branding: Optional[Dict[str, Any]] = None,
) -> bytes:
    branding = dict(branding or neutral_branding())
    if not branding.get("name"):
        branding["name"] = company
    accent = hex_to_rgb(branding.get("accent"))
    table_color = hex_to_rgb(branding.get("table"))
    document = fitz.open()
    try:
        page = None
        y = 0.0

        def new_page() -> Any:
            nonlocal page, y
            page = document.new_page(width=PAGE_W, height=PAGE_H)
            first = document.page_count == 1
            y = draw_header(page, branding, "Estado de cuenta" if first else "Estado de cuenta (continuación)", margin=MARGIN)
            if first:
                page.insert_text((MARGIN, y), str(client.get("name") or ""), fontname="hebo", fontsize=12, color=TEXT)
                y += 16
                details = [f"Fecha: {_date(as_of)}"]
                if client.get("vat"):
                    details.insert(0, f"Documento: {client['vat']}")
                page.insert_text((MARGIN, y), "   ·   ".join(details), fontname="helv", fontsize=9, color=MUTED)
                y += 22
            else:
                page.insert_text((MARGIN, y), str(client.get("name") or ""), fontname="helv", fontsize=9, color=MUTED)
                y += 24
            page.draw_rect(fitz.Rect(MARGIN, y - 13, PAGE_W - MARGIN, y + 6), color=None, fill=table_color)
            x = MARGIN
            for title, width, right in COLUMNS:
                _cell(page, x, y, width, title, right, size=8.5, color=WHITE, bold=True)
                x += width
            y += ROW_H + 2
            return page

        new_page()
        for index, invoice in enumerate(invoices):
            if y > PAGE_H - MARGIN - 70:
                new_page()
            if index % 2:
                page.draw_rect(fitz.Rect(MARGIN, y - 12.5, PAGE_W - MARGIN, y + 5.5), color=None, fill=(0.965, 0.97, 0.975))
            currency = invoice.get("currency") or "UYU"
            overdue = int(invoice.get("days_overdue") or 0)
            values = [
                (f"{invoice['label']} " if invoice.get("label") else "Nota de crédito " if invoice.get("is_refund") else "") + str(invoice.get("name") or ""),
                _date(invoice.get("invoice_date")),
                _date(invoice.get("due_date")),
                str(overdue) if overdue > 0 else "-",
                format_money(float(invoice.get("amount_total") or 0), currency),
                format_money(float(invoice.get("residual") or 0), currency),
            ]
            x = MARGIN
            for (title, width, right), value in zip(COLUMNS, values):
                color = accent if title == "Días venc." and overdue > 0 else TEXT
                _cell(page, x, y, width, value, right, color=color)
                x += width
            y += ROW_H

        y += 4
        page.draw_line((MARGIN, y - 12), (PAGE_W - MARGIN, y - 12), color=table_color, width=0.8)
        totals = client.get("balance_by_currency") or {}
        overdue_totals = client.get("overdue_by_currency") or {}
        for currency in sorted(totals):
            if y > PAGE_H - MARGIN - 50:
                new_page()
            label = f"Saldo total {currency}"
            _cell(page, PAGE_W - MARGIN - 300, y, 200, label, True, bold=True)
            _cell(page, PAGE_W - MARGIN - 100, y, 100, format_money(totals[currency], currency), True, bold=True)
            y += ROW_H
            if overdue_totals.get(currency):
                _cell(page, PAGE_W - MARGIN - 300, y, 200, f"Vencido {currency}", True, color=accent, bold=True)
                _cell(page, PAGE_W - MARGIN - 100, y, 100, format_money(overdue_totals[currency], currency), True, color=accent, bold=True)
                y += ROW_H

        for index, current in enumerate(document, start=1):
            draw_footer(current, branding, f"Estado de cuenta al {_date(as_of)} · Página {index} de {document.page_count}", margin=MARGIN)
        document.set_metadata({"title": f"Estado de cuenta - {client.get('name') or ''}", "author": branding.get("name") or "", "creator": "EtiquetadorZPL"})
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()
