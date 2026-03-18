"""
Helpers compartidos para imprimir orden/etiqueta con fallback de impresoras.
Centraliza la logica para evitar duplicacion entre worker y endpoints.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from administrado_integration import administrado_integration
from odoo_integration import odoo_integration

_LABEL_COPIES_LOCK = threading.Lock()


def _safe_int(value: Any, default: int = 1, min_value: int = 1, max_value: int = 10) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if number < min_value:
        number = min_value
    if number > max_value:
        number = max_value
    return number


def print_order_pdf_with_fallback(
    *,
    envio_id: str,
    pdf_bytes: bytes,
    preferred_printer: str = "",
    copies: Optional[int] = None,
) -> Dict[str, Any]:
    primary = preferred_printer.strip() or str(odoo_integration.config.get("default_order_printer", "")).strip()
    fallback = str(odoo_integration.config.get("fallback_order_printer", "")).strip()
    safe_copies = _safe_int(
        copies if copies is not None else odoo_integration.config.get("default_order_copies", 1),
        default=1,
        min_value=1,
        max_value=10,
    )

    if not primary:
        raise ValueError("No hay impresora configurada para la orden Odoo")

    try:
        result = odoo_integration.print_order_pdf(pdf_bytes, envio_id, printer=primary, copies=safe_copies)
        if result.get("success"):
            return result
    except Exception as exc:
        result = {"success": False, "printer": primary, "error": str(exc)}

    if fallback and fallback != primary:
        try:
            fallback_result = odoo_integration.print_order_pdf(
                pdf_bytes,
                envio_id,
                printer=fallback,
                copies=safe_copies,
            )
            if fallback_result.get("success"):
                return fallback_result
            result = fallback_result
        except Exception as exc:
            result = {"success": False, "printer": fallback, "error": str(exc)}

    return result


def download_and_print_order_with_fallback(
    *,
    envio_id: str,
    order_id: int,
    preferred_printer: str = "",
    auth_override: Optional[Dict[str, str]] = None,
    report_name: str = "",
    copies: Optional[int] = None,
) -> Dict[str, Any]:
    selected_report = (report_name or str(odoo_integration.config.get("report_name", ""))).strip()
    pdf_bytes = odoo_integration.download_sale_order_report_pdf(
        order_id=order_id,
        report_name=selected_report,
        auth_override=auth_override,
    )
    return print_order_pdf_with_fallback(
        envio_id=envio_id,
        pdf_bytes=pdf_bytes,
        preferred_printer=preferred_printer,
        copies=copies,
    )


def print_label_pdf_with_fallback(
    *,
    envio_id: str,
    pdf_bytes: bytes,
    preferred_printer: str = "",
    copies: Optional[int] = None,
) -> Dict[str, Any]:
    primary = preferred_printer.strip() or str(odoo_integration.config.get("default_label_printer", "")).strip()
    fallback = str(odoo_integration.config.get("fallback_label_printer", "")).strip()
    safe_copies = _safe_int(
        copies if copies is not None else odoo_integration.config.get("default_label_copies", 1),
        default=1,
        min_value=1,
        max_value=10,
    )

    if not primary:
        primary = str(administrado_integration.get_default_printer() or "").strip()
    if not primary:
        raise ValueError("No hay impresora configurada para etiqueta")

    def _print(printer_name: str) -> Dict[str, Any]:
        with _LABEL_COPIES_LOCK:
            previous_copies = administrado_integration.config.get("default_copies", 1)
            try:
                administrado_integration.config["default_copies"] = safe_copies
                return administrado_integration.process_downloaded_pdf(pdf_bytes, envio_id, printer=printer_name)
            finally:
                administrado_integration.config["default_copies"] = previous_copies

    try:
        result = _print(primary)
        if result.get("success"):
            return result
    except Exception as exc:
        result = {"success": False, "printer": primary, "error": str(exc)}

    if fallback and fallback != primary:
        try:
            fallback_result = _print(fallback)
            if fallback_result.get("success"):
                return fallback_result
            result = fallback_result
        except Exception as exc:
            result = {"success": False, "printer": fallback, "error": str(exc)}

    return result


def download_and_print_label_with_fallback(
    *,
    envio_id: str,
    preferred_printer: str = "",
    copies: Optional[int] = None,
) -> Dict[str, Any]:
    pdf_bytes = administrado_integration.download_label_pdf(envio_id)
    return print_label_pdf_with_fallback(
        envio_id=envio_id,
        pdf_bytes=pdf_bytes,
        preferred_printer=preferred_printer,
        copies=copies,
    )
