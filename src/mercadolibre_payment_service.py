"""Conciliacion asistida de pagos Mercado Libre contra facturas de Odoo.

Una venta de Mercado Libre puede tener varias ordenes agrupadas en un pack.
Odoo identifica la venta por ``pack_id`` (o por ``order_id`` si no hay pack) y
la factura incluye el envio pagado por el comprador, por eso el importe a
conciliar es la suma de productos de todas las ordenes mas el costo de envio.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from company_branding import get_branding
from mercadolibre_payment_pdf import (
    build_mercadolibre_payment_filename,
    generate_mercadolibre_payment_pdf,
)


_register_lock = threading.Lock()

# Odoo puede facturar un centesimo por encima o por debajo del total cobrado
# por Mercado Libre al redondear impuestos linea a linea. Esa diferencia se
# contabiliza en la cuenta de redondeos, igual que en Conciliacion POS.
ROUNDING_TOLERANCE = 0.01
ROUNDING_WRITEOFF_LABEL = "Redondeo cobro Mercado Libre"


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date_iso(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10] if len(text) >= 10 else ""


def summarize_order_payment(order: Dict[str, Any]) -> Dict[str, Any]:
    """Resume una orden individual. ``amount`` es solo productos, sin envio."""
    payments = [item for item in (order.get("payments") or []) if isinstance(item, dict)]
    approved = [item for item in payments if str(item.get("status") or "").lower() == "approved"]
    relevant = approved or payments
    paid_amount = _as_float(order.get("paid_amount"))
    if paid_amount <= 0:
        paid_amount = sum(_as_float(item.get("transaction_amount")) for item in approved)
    if paid_amount <= 0 and str(order.get("status") or "").lower() == "paid":
        paid_amount = _as_float(order.get("total_amount"))

    payment_date = ""
    for payment in relevant:
        payment_date = _date_iso(
            payment.get("date_approved")
            or payment.get("date_last_modified")
            or payment.get("date_created")
        )
        if payment_date:
            break
    if not payment_date:
        payment_date = _date_iso(order.get("date_closed") or order.get("date_created"))

    payment_ids = [str(item.get("id")) for item in relevant if item.get("id") not in (None, "")]
    methods = [
        str(item.get("payment_method_id") or item.get("payment_type") or item.get("payment_type_id"))
        for item in relevant
        if item.get("payment_method_id") or item.get("payment_type") or item.get("payment_type_id")
    ]
    buyer = order.get("buyer") or {}
    return {
        "order_id": str(order.get("id") or ""),
        "order_status": str(order.get("status") or ""),
        "payment_ids": payment_ids,
        "approved_payment_count": len(approved),
        "payment_reference": ", ".join(payment_ids),
        "payment_statuses": [str(item.get("status") or "") for item in relevant],
        "payment_methods": list(dict.fromkeys(methods)),
        "payment_method": ", ".join(dict.fromkeys(methods)),
        "amount": round(paid_amount, 2),
        "currency": str(order.get("currency_id") or ""),
        "payment_date": payment_date,
        "buyer": str(buyer.get("nickname") or buyer.get("id") or ""),
        "shipment_id": str((order.get("shipping") or {}).get("id") or ""),
    }


def sale_reference(order: Dict[str, Any]) -> str:
    """Referencia con la que Odoo identifica la venta: el pack si existe."""
    return str(order.get("pack_id") or order.get("id") or "")


def _load_sale_orders(
    mercadolibre: Any,
    order: Dict[str, Any],
    cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Devuelve todas las ordenes del pack de ``order`` (o solo ella si no hay pack)."""
    cache = cache if cache is not None else {}
    cache[str(order.get("id"))] = order
    pack_id = str(order.get("pack_id") or "")
    if not pack_id:
        return [order]
    pack = mercadolibre.get_pack(pack_id)
    order_ids = [
        str((item or {}).get("id") or "")
        for item in (pack.get("orders") or [])
        if (item or {}).get("id")
    ]
    if not order_ids:
        raise ValueError(f"Mercado Libre no devolvio las ordenes del pack {pack_id}")
    orders: List[Dict[str, Any]] = []
    for order_id in dict.fromkeys(order_ids):
        if order_id not in cache:
            cache[order_id] = mercadolibre.get_order(order_id)
        orders.append(cache[order_id])
    return orders


def _shipment_id(orders: List[Dict[str, Any]]) -> str:
    for order in orders:
        shipment_id = str((order.get("shipping") or {}).get("id") or "")
        if shipment_id:
            return shipment_id
    return ""


def _buyer_shipping_cost(mercadolibre: Any, orders: List[Dict[str, Any]]) -> float:
    """Envio pagado por el comprador; se cobra una sola vez por pack/shipment."""
    shipment_id = _shipment_id(orders)
    if shipment_id:
        costs = mercadolibre.get_shipment_costs(shipment_id)
        return round(_as_float((costs.get("receiver") or {}).get("cost")), 2)
    return 0.0


def summarize_sale_payment(orders: List[Dict[str, Any]], shipping_cost: float) -> Dict[str, Any]:
    """Resume una venta (orden suelta o pack) sumando productos y envio."""
    summaries = [summarize_order_payment(order) for order in orders]
    first = summaries[0]
    payment_ids = list(dict.fromkeys(pid for item in summaries for pid in item["payment_ids"]))
    methods = list(dict.fromkeys(m for item in summaries for m in item["payment_methods"]))
    statuses = {item["order_status"].lower() for item in summaries}
    products_amount = round(sum(item["amount"] for item in summaries), 2)
    shipping_amount = round(_as_float(shipping_cost), 2)
    payment_dates = sorted(item["payment_date"] for item in summaries if item["payment_date"])
    return {
        "order_id": first["order_id"],
        "order_ids": [item["order_id"] for item in summaries],
        "pack_id": str(orders[0].get("pack_id") or ""),
        "reference": sale_reference(orders[0]),
        "order_status": ", ".join(sorted(statuses)),
        "all_orders_paid": statuses == {"paid"},
        "payment_ids": payment_ids,
        "approved_payment_count": sum(item["approved_payment_count"] for item in summaries),
        "payment_reference": ", ".join(payment_ids),
        "payment_method": ", ".join(methods),
        "products_amount": products_amount,
        "shipping_amount": shipping_amount,
        "amount": round(products_amount + shipping_amount, 2),
        "currency": first["currency"],
        "payment_date": payment_dates[-1] if payment_dates else first["payment_date"],
        "buyer": first["buyer"],
        "shipment_id": _shipment_id(orders),
    }


def _sale_document(orders: List[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, Any]:
    """Dict con forma de orden que representa la venta completa para el PDF."""
    return {
        **orders[0],
        "id": summary["reference"],
        "pack_id": summary["pack_id"],
        "order_ids": summary["order_ids"],
        "total_amount": summary["products_amount"],
        "shipping_amount": summary["shipping_amount"],
        "paid_amount": summary["amount"],
        "payments": [payment for order in orders for payment in (order.get("payments") or [])],
        "order_items": [line for order in orders for line in (order.get("order_items") or [])],
    }


def _unusable_reason(summary: Dict[str, Any]) -> str:
    if not summary["all_orders_paid"]:
        return "La venta tiene ordenes que no estan pagadas"
    if summary["amount"] <= 0:
        return "Mercado Libre no devolvio un importe pagado"
    if not summary["payment_ids"] or summary["approved_payment_count"] <= 0:
        return "Mercado Libre no devolvio un pago aprobado con ID"
    return ""


def _rounding_difference(summary: Dict[str, Any], invoice: Dict[str, Any]) -> float:
    """Saldo de la factura menos lo cobrado en Mercado Libre (0 si coincide)."""
    return round(_as_float(invoice.get("amount_due")) - summary["amount"], 2)


def _load_paid_sales(mercadolibre: Any, limit: int) -> List[List[Dict[str, Any]]]:
    data = mercadolibre.search_orders(limit=limit, offset=0, status="paid")
    cache: Dict[str, Dict[str, Any]] = {}
    sales: Dict[str, List[Dict[str, Any]]] = {}
    for listed in data.get("results", []) or []:
        listed = listed or {}
        order_id = str(listed.get("id") or "")
        if not order_id or (listed.get("pack_id") and str(listed["pack_id"]) in sales):
            continue
        # La busqueda puede omitir campos de pago segun el site. Consultar el
        # detalle evita registrar usando un resumen incompleto o desactualizado.
        order = cache.get(order_id) or mercadolibre.get_order(order_id)
        reference = sale_reference(order)
        if reference not in sales:
            sales[reference] = _load_sale_orders(mercadolibre, order, cache)
    return list(sales.values())


def build_payment_proposal(mercadolibre: Any, odoo: Any, limit: int = 20) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for orders in _load_paid_sales(mercadolibre, limit):
        try:
            summary = summarize_sale_payment(orders, _buyer_shipping_cost(mercadolibre, orders))
        except Exception as exc:
            first = orders[0]
            items.append({
                **summarize_order_payment(first),
                "reference": sale_reference(first),
                "can_register": False,
                "reason": str(exc or "").strip() or "No se pudo consultar el envio en Mercado Libre",
            })
            continue
        item: Dict[str, Any] = {**summary, "can_register": False, "reason": _unusable_reason(summary)}
        if not item["reason"]:
            try:
                match = odoo.find_sale_invoice_for_reference(
                    summary["reference"],
                    summary["amount"],
                    summary["currency"],
                )
                item.update(match)
                item["can_register"] = bool(match.get("can_register"))
                if item["can_register"]:
                    item["rounding_difference"] = _rounding_difference(summary, match["invoice"])
            except Exception as exc:
                item["reason"] = str(exc or "").strip() or "No se pudo consultar la factura Odoo"
        items.append(item)
    return {
        "items": items,
        "count": len(items),
        "ready_count": sum(bool(item.get("can_register")) for item in items),
    }


def register_order_payment(
    mercadolibre: Any,
    odoo: Any,
    *,
    order_id: str,
    journal_id: int,
    auth_override: Optional[Dict[str, str]],
    rounding_account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Registra el pago de la venta a la que pertenece ``order_id`` (todo su pack).

    Se registra el importe cobrado por Mercado Libre; si la factura difiere por
    redondeo, el centesimo se salda contra ``rounding_account_id``.
    """
    with _register_lock:
        orders = _load_sale_orders(mercadolibre, mercadolibre.get_order(str(order_id)))
        summary = summarize_sale_payment(orders, _buyer_shipping_cost(mercadolibre, orders))
        if not summary["all_orders_paid"]:
            raise ValueError("La venta de Mercado Libre ya no figura como pagada")
        if _unusable_reason(summary):
            raise ValueError("Mercado Libre no devolvio un pago aprobado utilizable")

        match = odoo.find_sale_invoice_for_reference(
            summary["reference"],
            summary["amount"],
            summary["currency"],
            auth_override=auth_override,
        )
        if not match.get("can_register"):
            raise ValueError(str(match.get("reason") or "No se encontro una factura pendiente compatible"))

        invoice = match["invoice"]
        invoice_name = str(invoice.get("name") or invoice.get("id") or "")
        memo = f"{invoice_name} - {summary['reference']}"
        rounding_difference = _rounding_difference(summary, invoice)
        if abs(rounding_difference) > ROUNDING_TOLERANCE:
            raise ValueError("El importe de Mercado Libre no coincide con el saldo de la factura")
        if rounding_difference and not rounding_account_id:
            raise ValueError(
                f"La factura difiere en {rounding_difference:+.2f} por redondeo: "
                "selecciona la cuenta de redondeo"
            )
        payment_result = odoo.register_invoice_payment(
            int(invoice["id"]),
            float(summary["amount"]),
            summary["payment_date"],
            int(journal_id),
            memo,
            auth_override,
            True,
            int(rounding_account_id) if rounding_difference else None,
            writeoff_label=ROUNDING_WRITEOFF_LABEL,
        )
        result: Dict[str, Any] = {
            "ok": True,
            "order": summary,
            "invoice": invoice,
            "sale_order": match.get("sale_order"),
            "memo": memo,
            "payment_amount": summary["amount"],
            "rounding_difference": rounding_difference,
            "result": payment_result,
            "attachment_ok": False,
        }

        payment_id = payment_result.get("payment_id")
        if not payment_id:
            result["warning"] = (
                "El pago se registro, pero Odoo no devolvio el ID del pago creado "
                "para adjuntar el PDF de Mercado Libre."
            )
            return result

        try:
            sale = _sale_document(orders, summary)
            filename = build_mercadolibre_payment_filename(sale)
            pdf_bytes = generate_mercadolibre_payment_pdf(sale, invoice_name, get_branding(odoo))
            result["attachment"] = odoo.attach_pdf_to_payment(
                int(payment_id),
                filename,
                pdf_bytes,
                auth_override,
            )
            result["attachment_ok"] = True
        except Exception as exc:
            message = str(exc or "").strip() or "error desconocido"
            result["warning"] = (
                "El pago se registro, pero no se pudo adjuntar el PDF de Mercado Libre: "
                f"{message}"
            )

        result["payment_url"] = odoo.record_url("account.payment", payment_id)
        result["invoice_url"] = odoo.record_url("account.move", invoice["id"])
        return result
