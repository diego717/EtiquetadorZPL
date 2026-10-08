"""
Motor de conciliacion de pagos POS: cruza cupones de TotalNet contra facturas
pendientes de cobro en Odoo. Nunca decide solo -- siempre propone candidatos
para que un operador confirme antes de registrar nada en Odoo.
"""

from __future__ import annotations

import itertools
import json
import logging
import re
import threading
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_AMOUNT_TOLERANCE = 0.01
DEFAULT_DATE_WINDOW_DAYS = 2
DEFAULT_SETTLEMENT_LOOKAHEAD_DAYS = 15
MAX_GROUP_SIZE = 4  # Solo lo usa el comparador historico privado.
DEFAULT_AUTO_SYNC_INTERVAL_MINUTES = 60
DEFAULT_AUTO_SYNC_LOOKBACK_DAYS = 7
HISTORY_LIMIT = 200

# Serializa las escrituras del estado: TotalNet y Mercado Libre comparten el
# mismo historial de pagos registrados.
_state_lock = threading.Lock()


def _resolve_state_path(filename: str) -> Path:
    try:
        from config_manager import config_manager

        return Path(config_manager.get_config_directory()) / filename
    except Exception:
        import os

        if os.name == "nt":
            base_dir = Path(os.environ.get("APPDATA", "."))
        else:
            base_dir = Path.home() / ".config"
        config_dir = base_dir / "EtiquetadorZPL"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / filename


def _parse_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "")).date()
    except ValueError:
        pass
    # Ultimo recurso: si arranca con YYYY-MM-DD seguido de cualquier otra cosa
    # (ej. milisegundos), quedarse solo con los primeros 10 caracteres.
    if len(text) >= 10:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def normalize_date_iso(value: Any) -> str:
    """Convierte fechas de TotalNet/Odoo a YYYY-MM-DD para los wizards de Odoo."""
    parsed = _parse_date(value)
    if parsed is None:
        raise ValueError(f"Fecha de pago invalida: {value or '-'}")
    return parsed.isoformat()


def _cupon_field(cupon: Dict[str, Any], dotted_key: str) -> Any:
    """Soporta tanto claves anidadas dict (transaccion: {...}) como planas (transaccion.importe)."""
    if dotted_key in cupon:
        return cupon.get(dotted_key)
    parts = dotted_key.split(".")
    node: Any = cupon
    for part in parts:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def resolve_settlement_query_range(date_from: str, date_to: str, lookahead_days: int) -> Tuple[str, str]:
    """TotalNet expone /cupones por fecha de liquidacion, no por fecha de venta:
    un cupon suele liquidar varios dias habiles despues de la venta. Para no
    perder ventas recientes que todavia no liquidaron, hay que consultar un
    rango de liquidacion mas amplio que el rango de venta que pidio el operador.
    """
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if start is None or end is None:
        raise ValueError(f"Rango de fechas invalido: {date_from} - {date_to}")
    extended_end = end + timedelta(days=max(0, lookahead_days))
    yesterday = date.today() - timedelta(days=1)
    if extended_end > yesterday:
        extended_end = yesterday
    if extended_end < start:
        extended_end = start
    return start.isoformat(), extended_end.isoformat()


def filter_cupones_by_transaction_date(
    cupones: List[Dict[str, Any]], date_from: str, date_to: str
) -> List[Dict[str, Any]]:
    """Vuelve a acotar los cupones traidos con resolve_settlement_query_range
    (rango de liquidacion ampliado) a la fecha de venta que pidio el operador.
    """
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if start is None or end is None:
        return list(cupones)
    filtered = []
    for cupon in cupones:
        transaction_date = _parse_date(_cupon_field(cupon, "transaccion.fecha_cupon"))
        if transaction_date is None or start <= transaction_date <= end:
            filtered.append(cupon)
    return filtered


def _currency_label(value: Any) -> str:
    """Obtiene un código/nombre legible desde un campo monetario de Odoo/API."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        value = value[1]
    elif isinstance(value, dict):
        value = value.get("name") or value.get("code") or value.get("currency")
    return str(value or "").strip()


def _currency_code(value: Any) -> str:
    """Normaliza nombres habituales para no cruzar UYU con USD."""
    text = unicodedata.normalize("NFKD", _currency_label(value))
    text = "".join(char for char in text if not unicodedata.combining(char)).upper()
    # TotalNet informa la moneda con el codigo ISO 4217 numerico. Odoo suele
    # devolver el codigo alfabetico, por lo que ambos formatos deben converger
    # antes de comparar una factura con un cupon.
    numeric_codes = {
        "858": "UYU",
        "840": "USD",
        "978": "EUR",
    }
    if text in numeric_codes:
        return numeric_codes[text]
    if "USD" in text or "DOLAR" in text:
        return "USD"
    if "UYU" in text or "PESO" in text or "URUGUAY" in text:
        return "UYU"
    if "EUR" in text or "EURO" in text:
        return "EUR"
    return text


def _cupon_summary(cupon: Dict[str, Any]) -> Dict[str, Any]:
    raw_currency = _cupon_field(cupon, "transaccion.moneda")
    tax_discount = _cupon_field(cupon, "transaccion.importe_devolución_impuesto")
    if tax_discount is None:
        tax_discount = _cupon_field(cupon, "transaccion.importe_devolucion_impuesto")
    amount = _cupon_field(cupon, "transaccion.importe")
    try:
        total_paid = round(float(amount) - float(tax_discount), 2) if tax_discount else float(amount)
    except (TypeError, ValueError):
        total_paid = None
    return {
        "cupon_id": _cupon_field(cupon, "transaccion.cupon_id"),
        "ticket": _cupon_field(cupon, "transaccion.ticket"),
        "autorizacion": _cupon_field(cupon, "transaccion.autorizacion"),
        "lote": _cupon_field(cupon, "transaccion.lote"),
        "numero_factura": _cupon_field(cupon, "transaccion.numero_factura"),
        "importe": amount,
        "moneda": _currency_code(raw_currency) or _currency_label(raw_currency),
        "moneda_original": raw_currency,
        "fecha": _cupon_field(cupon, "transaccion.fecha_cupon"),
        "sello": _cupon_field(cupon, "transaccion.sello"),
        "producto": _cupon_field(cupon, "transaccion.producto"),
        "terminal": _cupon_field(cupon, "transaccion.terminal"),
        "canal": _cupon_field(cupon, "transaccion.canal"),
        "modo": _cupon_field(cupon, "transaccion.modo"),
        "bin": _cupon_field(cupon, "transaccion.bin"),
        "propina": _cupon_field(cupon, "transaccion.propina"),
        "cuotas": _cupon_field(cupon, "transaccion.cuotas"),
        "ultimos_4_digitos": _cupon_field(cupon, "transaccion.ultimos_4_Digitos"),
        "devolucion_impuesto": _cupon_field(cupon, "transaccion.devolucion_impuesto"),
        "importe_devolucion_impuesto": tax_discount,
        "total_pagado": total_paid,
        "fecha_liquidacion": _cupon_field(cupon, "liquidacion.fecha_liquidacion"),
        "fecha_pago": _cupon_field(cupon, "liquidacion.fecha_pago"),
        "forma_pago": _cupon_field(cupon, "liquidacion.forma_de_pago"),
        "banco_acreditacion": _cupon_field(cupon, "liquidacion.banco_acreditacion"),
        "plan_venta": _cupon_field(cupon, "liquidacion.plan_venta"),
        "manual_entry": _cupon_field(cupon, "transaccion.origen") == "ticket_manual",
    }


def _invoice_summary(invoice: Dict[str, Any]) -> Dict[str, Any]:
    partner = invoice.get("partner_id")
    partner_name = partner[1] if isinstance(partner, (list, tuple)) and len(partner) >= 2 else partner
    payment_state = str(invoice.get("invoice_payment_state") or "").strip()
    return {
        "invoice_id": invoice.get("id"),
        "name": invoice.get("name"),
        "partner": partner_name,
        "amount_total": invoice.get("amount_total"),
        "amount_residual": invoice.get("amount_residual"),
        "currency": _currency_label(invoice.get("currency_id")),
        "invoice_date": invoice.get("invoice_date"),
        "payment_state": payment_state,
        "can_register_payment": payment_state in {"not_paid", "partial"},
    }


def _invoice_number(value: Any) -> str:
    """Normaliza el ultimo bloque numerico de identificadores como A-49890."""
    matches = re.findall(r"\d+", str(value or ""))
    if not matches:
        return ""
    try:
        return str(int(matches[-1]))
    except ValueError:
        return ""


def round_payment_amount(value: Any) -> float:
    """Redondea al peso con regla comercial: 0,50 siempre hacia arriba."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Importe invalido para redondear: {value}")
    return float(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _match_summary(
    cupon: Dict[str, Any],
    invoice: Dict[str, Any],
    matched_by: str,
    amount_tolerance: float,
) -> Dict[str, Any]:
    coupon_summary = _cupon_summary(cupon)
    invoice_summary = _invoice_summary(invoice)
    try:
        coupon_amount = float(coupon_summary.get("importe"))
        invoice_amount = float(invoice_summary.get("amount_total"))
        amount_difference = round(invoice_amount - coupon_amount, 2)
        # Un pago POS debe cancelar el total exacto de la factura. La tolerancia
        # solo sirve para encontrar candidatos; nunca autoriza una diferencia
        # contable al confirmar el pago.
        amount_matches = amount_difference == 0
        # TotalNet puede informar el importe original con centesimos o el peso
        # entero ya cobrado. Para una diferencia, solo aceptar el segundo caso:
        # el cupon debe ser exactamente el entero esperado desde Odoo.
        rounding_matches = round(
            coupon_amount - round_payment_amount(invoice_amount), 2
        ) == 0
    except (TypeError, ValueError):
        amount_difference = None
        amount_matches = False
        rounding_matches = False

    coupon_currency = _currency_code(coupon_summary.get("moneda"))
    invoice_currency = _currency_code(invoice.get("currency_id"))
    currency_matches = not (
        coupon_currency and invoice_currency and coupon_currency != invoice_currency
    )
    can_confirm = bool(
        invoice_summary.get("can_register_payment")
        and (amount_matches or rounding_matches)
        and currency_matches
    )
    return {
        "cupon": coupon_summary,
        "invoice": invoice_summary,
        "matched_by": matched_by,
        "amount_matches": amount_matches,
        "amount_difference": amount_difference,
        "rounding_matches": rounding_matches,
        "requires_rounding_writeoff": bool(not amount_matches and rounding_matches),
        "currency_matches": currency_matches,
        "can_confirm": can_confirm,
    }


def _default_recon_config() -> Dict[str, Any]:
    return {
        "amount_tolerance": DEFAULT_AMOUNT_TOLERANCE,
        "date_window_days": DEFAULT_DATE_WINDOW_DAYS,
        "settlement_lookahead_days": DEFAULT_SETTLEMENT_LOOKAHEAD_DAYS,
        # Mapeo "sello" de TotalNet (ej. "MasterCard") -> id de diario contable en Odoo.
        "journal_map": {},
        # Conciliacion en segundo plano: sincroniza y deja la propuesta lista para revisar.
        "auto_sync_enabled": False,
        "auto_sync_interval_minutes": DEFAULT_AUTO_SYNC_INTERVAL_MINUTES,
        "auto_sync_lookback_days": DEFAULT_AUTO_SYNC_LOOKBACK_DAYS,
        "auto_sync_notify_desktop": True,
        # Registro automatico SOLO de coincidencias deterministicas (ver
        # find_deterministic_matches). Apagado por defecto.
        "auto_register_deterministic": False,
        "auto_register_operator": "",
    }


def load_recon_config() -> Dict[str, Any]:
    path = _resolve_state_path("pos_reconciliation_config.json")
    config = _default_recon_config()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                config.update(json.load(handle))
        except Exception as exc:
            logger.warning("No se pudo leer config de conciliacion POS: %s", exc)
    return config


def save_recon_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    config = load_recon_config()
    config.update(updates)
    path = _resolve_state_path("pos_reconciliation_config.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=True)
    return config


def resolve_journal_id(sello: Any, journal_map: Dict[str, Any]) -> Optional[int]:
    key = str(sello or "").strip()
    if not key:
        return None
    value = journal_map.get(key)
    if value is None:
        # Intento case-insensitive por si el sello viene con distinta capitalizacion.
        for map_key, map_value in journal_map.items():
            if str(map_key).strip().lower() == key.lower():
                value = map_value
                break
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def build_payment_memo(invoice_name: Any, cupon: Dict[str, Any]) -> str:
    if cupon.get("manual_entry"):
        # Ticket cargado a mano: el operador ya lo tipeo, no hace falta repetir
        # el resto de los datos del comprobante en el memo del pago.
        parts = []
        ticket = cupon.get("ticket")
        if ticket:
            parts.append(f"Ticket {ticket}")
        lote = cupon.get("lote")
        if lote:
            parts.append(f"Lote {lote}")
        return " | ".join(parts)

    parts = [f"Factura Odoo {invoice_name}"] if invoice_name else []
    totalnet_invoice = cupon.get("numero_factura")
    if totalnet_invoice is not None:
        parts.append(f"TotalNet Fact. {totalnet_invoice}")
    lote = cupon.get("lote")
    if lote is not None:
        parts.append(f"Lote {lote}")
    ticket = cupon.get("ticket")
    if ticket is not None:
        parts.append(f"Ticket {ticket}")
    authorization = cupon.get("autorizacion")
    if authorization:
        parts.append(f"Aut. {authorization}")
    card = " ".join(
        str(value).title()
        for value in (cupon.get("sello"), cupon.get("producto"))
        if value
    )
    if card:
        parts.append(card)
    amount = cupon.get("importe")
    currency = cupon.get("moneda") or ""
    if amount is not None:
        parts.append(f"Importe {currency} {float(amount):.2f}".strip())
    tax_discount = cupon.get("importe_devolucion_impuesto")
    if tax_discount:
        parts.append(f"Desc. Ley 19.210 {currency} {float(tax_discount):.2f}".strip())
        total_paid = cupon.get("total_pagado")
        if total_paid is not None:
            parts.append(f"Total cobrado {currency} {float(total_paid):.2f}".strip())
    last_four = str(cupon.get("ultimos_4_digitos") or "").strip()
    if last_four:
        parts.append(f"****{last_four}")
    terminal = cupon.get("terminal")
    if terminal:
        parts.append(f"Terminal {terminal}")
    return " | ".join(parts)


def load_state() -> Dict[str, Any]:
    path = _resolve_state_path("pos_reconciliation_state.json")
    if not path.exists():
        return {"processed_cupon_ids": [], "history": []}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logger.warning("No se pudo leer estado de conciliacion POS: %s", exc)
        return {"processed_cupon_ids": [], "history": []}


def load_processed_cupon_ids() -> set:
    data = load_state()
    return {str(item) for item in data.get("processed_cupon_ids", [])}


def _append_history(
    payment_results: List[Dict[str, Any]],
    processed_cupon_ids: Optional[List[Any]] = None,
) -> None:
    path = _resolve_state_path("pos_reconciliation_state.json")
    with _state_lock:
        data = load_state()
        if processed_cupon_ids:
            processed = set(str(item) for item in data.get("processed_cupon_ids", []))
            processed.update(str(cid) for cid in processed_cupon_ids if cid is not None)
            data["processed_cupon_ids"] = sorted(processed)

        history = data.get("history", [])
        history.append({"at": datetime.now().isoformat(), "payments": payment_results})
        data["history"] = history[-HISTORY_LIMIT:]

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=True)


def mark_cupones_processed(cupon_ids: List[Any], payment_results: List[Dict[str, Any]]) -> None:
    _append_history(payment_results, cupon_ids)


def record_external_payments(payment_results: List[Dict[str, Any]]) -> None:
    """Agrega al historial pagos registrados fuera de TotalNet (ej. Mercado Libre)."""
    _append_history(payment_results)


def _legacy_match_cupones_to_invoices(
    cupones: List[Dict[str, Any]],
    invoices: List[Dict[str, Any]],
    amount_tolerance: float = DEFAULT_AMOUNT_TOLERANCE,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    exclude_cupon_ids: Optional[set] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    exclude_cupon_ids = exclude_cupon_ids or set()

    matches_unicos: List[Dict[str, Any]] = []
    ambiguos: List[Dict[str, Any]] = []
    sin_match: List[Dict[str, Any]] = []

    pending_invoices = [inv for inv in invoices if inv.get("id") is not None]

    def _candidates_for(cupon: Dict[str, Any]) -> List[Dict[str, Any]]:
        importe = _cupon_field(cupon, "transaccion.importe")
        fecha = _parse_date(_cupon_field(cupon, "transaccion.fecha_cupon"))
        if importe is None or fecha is None:
            return []
        try:
            importe_value = float(importe)
        except (TypeError, ValueError):
            return []

        found = []
        for invoice in pending_invoices:
            inv_amount = invoice.get("amount_total")
            inv_date = _parse_date(invoice.get("invoice_date"))
            if inv_amount is None or inv_date is None:
                continue
            try:
                inv_amount_value = float(inv_amount)
            except (TypeError, ValueError):
                continue
            if abs(inv_amount_value - importe_value) > amount_tolerance:
                continue
            coupon_currency = _currency_code(_cupon_field(cupon, "transaccion.moneda"))
            invoice_currency = _currency_code(invoice.get("currency_id"))
            if coupon_currency and invoice_currency and coupon_currency != invoice_currency:
                continue
            if abs((inv_date - fecha).days) > date_window_days:
                continue
            found.append(invoice)
        return found

    cupones_sin_1a1: List[Dict[str, Any]] = []

    for cupon in cupones:
        cupon_id = _cupon_field(cupon, "transaccion.cupon_id")
        if cupon_id is not None and str(cupon_id) in exclude_cupon_ids:
            continue

        candidates = _candidates_for(cupon)
        if len(candidates) == 1:
            matches_unicos.append(
                {
                    "cupon": _cupon_summary(cupon),
                    "invoice": _invoice_summary(candidates[0]),
                    "matched_by": "importe_fecha",
                }
            )
        elif len(candidates) > 1:
            ambiguos.append(
                {
                    "cupon": _cupon_summary(cupon),
                    "candidates": [_invoice_summary(inv) for inv in candidates],
                    "reason": "multiples_facturas_mismo_importe_fecha",
                }
            )
        else:
            cupones_sin_1a1.append(cupon)

    matched_invoice_ids = {m["invoice"]["invoice_id"] for m in matches_unicos}
    remaining_invoices = [inv for inv in pending_invoices if inv.get("id") not in matched_invoice_ids]

    grouped_cupon_ids = set()
    for invoice in remaining_invoices:
        inv_amount = invoice.get("amount_total")
        inv_date = _parse_date(invoice.get("invoice_date"))
        if inv_amount is None or inv_date is None:
            continue
        try:
            inv_amount_value = float(inv_amount)
        except (TypeError, ValueError):
            continue

        same_day_cupones = []
        for cupon in cupones_sin_1a1:
            cupon_id = _cupon_field(cupon, "transaccion.cupon_id")
            if cupon_id is not None and str(cupon_id) in grouped_cupon_ids:
                continue
            fecha = _parse_date(_cupon_field(cupon, "transaccion.fecha_cupon"))
            if fecha is None or abs((inv_date - fecha).days) > date_window_days:
                continue
            same_day_cupones.append(cupon)

        for group_size in range(2, min(MAX_GROUP_SIZE, len(same_day_cupones)) + 1):
            found_group = None
            for combo in itertools.combinations(same_day_cupones, group_size):
                total = 0.0
                valid = True
                for cupon in combo:
                    importe = _cupon_field(cupon, "transaccion.importe")
                    try:
                        total += float(importe)
                    except (TypeError, ValueError):
                        valid = False
                        break
                if valid and abs(total - inv_amount_value) <= amount_tolerance:
                    found_group = combo
                    break
            if found_group:
                ambiguos.append(
                    {
                        "cupon": None,
                        "cupones_grupo": [_cupon_summary(c) for c in found_group],
                        "candidates": [_invoice_summary(invoice)],
                        "reason": "posible_grupo_de_cupones_sumando_una_factura",
                    }
                )
                for cupon in found_group:
                    cupon_id = _cupon_field(cupon, "transaccion.cupon_id")
                    if cupon_id is not None:
                        grouped_cupon_ids.add(str(cupon_id))
                break

    for cupon in cupones_sin_1a1:
        cupon_id = _cupon_field(cupon, "transaccion.cupon_id")
        if cupon_id is not None and str(cupon_id) in grouped_cupon_ids:
            continue

        # Aunque la fecha no entre en la ventana automática, mostrar las
        # facturas pendientes cuyo importe coincide para que el operador pueda
        # confirmar la asociación manualmente.
        amount_candidates = []
        importe = _cupon_field(cupon, "transaccion.importe")
        try:
            importe_value = float(importe)
        except (TypeError, ValueError):
            importe_value = None

        if importe_value is not None:
            for invoice in pending_invoices:
                if invoice.get("id") in matched_invoice_ids:
                    continue
                try:
                    invoice_amount = float(invoice.get("amount_total"))
                except (TypeError, ValueError):
                    continue
                if abs(invoice_amount - importe_value) <= amount_tolerance:
                    coupon_currency = _currency_code(_cupon_field(cupon, "transaccion.moneda"))
                    invoice_currency = _currency_code(invoice.get("currency_id"))
                    if coupon_currency and invoice_currency and coupon_currency != invoice_currency:
                        continue
                    amount_candidates.append(_invoice_summary(invoice))

        sin_match.append(
            {
                "cupon": _cupon_summary(cupon),
                "amount_candidates": amount_candidates,
            }
        )

    return {"matches_unicos": matches_unicos, "ambiguos": ambiguos, "sin_match": sin_match}


def match_cupones_to_invoices(
    cupones: List[Dict[str, Any]],
    invoices: List[Dict[str, Any]],
    amount_tolerance: float = DEFAULT_AMOUNT_TOLERANCE,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    exclude_cupon_ids: Optional[set] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Concilia por numero de factura y usa importe/fecha solo como fallback.

    Las agrupaciones N-a-1 estan deliberadamente deshabilitadas: que varios
    cupones sumen una factura no demuestra que pertenezcan a esa venta.
    """
    exclude_cupon_ids = exclude_cupon_ids or set()
    matches_unicos: List[Dict[str, Any]] = []
    ambiguos: List[Dict[str, Any]] = []
    sin_match: List[Dict[str, Any]] = []

    available_invoices = [inv for inv in invoices if inv.get("id") is not None]
    invoice_number_index: Dict[str, List[Dict[str, Any]]] = {}
    for invoice in available_invoices:
        number = _invoice_number(invoice.get("name"))
        if number:
            invoice_number_index.setdefault(number, []).append(invoice)

    active_cupons: List[Dict[str, Any]] = []
    for cupon in cupones:
        cupon_id = _cupon_field(cupon, "transaccion.cupon_id")
        if cupon_id is not None and str(cupon_id) in exclude_cupon_ids:
            continue
        active_cupons.append(cupon)

    matched_invoice_ids: set = set()
    cupons_without_number_match: List[Dict[str, Any]] = []
    numbered_unmatched_cupons: List[Dict[str, Any]] = []

    # Nivel 1: numero de factura informado por TotalNet.
    for cupon in active_cupons:
        coupon_number = _invoice_number(
            _cupon_field(cupon, "transaccion.numero_factura")
        )
        candidates = invoice_number_index.get(coupon_number, []) if coupon_number else []
        candidates = [
            invoice
            for invoice in candidates
            if invoice.get("id") not in matched_invoice_ids
        ]
        if len(candidates) == 1:
            match = _match_summary(
                cupon,
                candidates[0],
                "numero_factura_totalnet",
                amount_tolerance,
            )
            matches_unicos.append(match)
            matched_invoice_ids.add(candidates[0].get("id"))
        elif len(candidates) > 1:
            ambiguos.append(
                {
                    "cupon": _cupon_summary(cupon),
                    "candidates": [_invoice_summary(inv) for inv in candidates],
                    "reason": "numero_factura_totalnet_duplicado_en_odoo",
                    "can_confirm": False,
                }
            )
        elif not coupon_number:
            cupons_without_number_match.append(cupon)
        else:
            # Si TotalNet informa un numero, es evidencia mas fuerte que una
            # coincidencia casual de importe/fecha. No adivinar otra factura.
            numbered_unmatched_cupons.append(cupon)

    def _amount_date_candidates(cupon: Dict[str, Any]) -> List[Dict[str, Any]]:
        importe = _cupon_field(cupon, "transaccion.importe")
        fecha = _parse_date(_cupon_field(cupon, "transaccion.fecha_cupon"))
        if importe is None or fecha is None:
            return []
        try:
            importe_value = float(importe)
        except (TypeError, ValueError):
            return []

        found: List[Dict[str, Any]] = []
        for invoice in available_invoices:
            if invoice.get("id") in matched_invoice_ids:
                continue
            inv_date = _parse_date(invoice.get("invoice_date"))
            try:
                inv_amount_value = float(invoice.get("amount_total"))
            except (TypeError, ValueError):
                continue
            if inv_date is None or abs(inv_amount_value - importe_value) > amount_tolerance:
                continue
            coupon_currency = _currency_code(
                _cupon_field(cupon, "transaccion.moneda")
            )
            invoice_currency = _currency_code(invoice.get("currency_id"))
            if coupon_currency and invoice_currency and coupon_currency != invoice_currency:
                continue
            if abs((inv_date - fecha).days) > date_window_days:
                continue
            found.append(invoice)
        return found

    # Nivel 2: importe, moneda y fecha solo si el numero no encontro factura.
    unmatched_cupons: List[Dict[str, Any]] = list(numbered_unmatched_cupons)
    for cupon in cupons_without_number_match:
        candidates = _amount_date_candidates(cupon)
        if len(candidates) == 1:
            match = _match_summary(
                cupon,
                candidates[0],
                "importe_fecha",
                amount_tolerance,
            )
            matches_unicos.append(match)
            matched_invoice_ids.add(candidates[0].get("id"))
        elif len(candidates) > 1:
            ambiguos.append(
                {
                    "cupon": _cupon_summary(cupon),
                    "candidates": [_invoice_summary(inv) for inv in candidates],
                    "reason": "multiples_facturas_mismo_importe_fecha",
                    "can_confirm": any(
                        _invoice_summary(inv).get("can_register_payment")
                        for inv in candidates
                    ),
                }
            )
        else:
            unmatched_cupons.append(cupon)

    for cupon in unmatched_cupons:
        amount_candidates: List[Dict[str, Any]] = []
        invoice_number_searched = _invoice_number(
            _cupon_field(cupon, "transaccion.numero_factura")
        )
        importe = _cupon_field(cupon, "transaccion.importe")
        try:
            importe_value = float(importe)
        except (TypeError, ValueError):
            importe_value = None

        if importe_value is not None and not invoice_number_searched:
            for invoice in available_invoices:
                if invoice.get("id") in matched_invoice_ids:
                    continue
                try:
                    invoice_amount = float(invoice.get("amount_total"))
                except (TypeError, ValueError):
                    continue
                if abs(invoice_amount - importe_value) > amount_tolerance:
                    continue
                coupon_currency = _currency_code(
                    _cupon_field(cupon, "transaccion.moneda")
                )
                invoice_currency = _currency_code(invoice.get("currency_id"))
                if coupon_currency and invoice_currency and coupon_currency != invoice_currency:
                    continue
                amount_candidates.append(_invoice_summary(invoice))

        sin_match.append(
            {
                "cupon": _cupon_summary(cupon),
                "amount_candidates": amount_candidates,
                "invoice_number_searched": invoice_number_searched,
            }
        )

    return {"matches_unicos": matches_unicos, "ambiguos": ambiguos, "sin_match": sin_match}


def _same_amount(left: Any, right: Any) -> bool:
    try:
        return round(float(left) - float(right), 2) == 0
    except (TypeError, ValueError):
        return False


def deterministic_rejection_reason(match: Dict[str, Any], invoice_number_counts: Dict[str, int]) -> str:
    """Devuelve "" si la coincidencia puede registrarse sin intervencion humana.

    Es deliberadamente mas estricta que `can_confirm`: exige numero de factura
    informado por TotalNet, importe exacto sin redondeo ni diferencia, factura
    sin pagos previos, diario resuelto por el mapeo y que ningun otro cupon del
    lote reclame el mismo numero de factura.
    """
    cupon = match.get("cupon") or {}
    invoice = match.get("invoice") or {}
    if match.get("matched_by") != "numero_factura_totalnet":
        return "no_coincide_por_numero_de_factura"
    if cupon.get("manual_entry"):
        return "ticket_manual"
    if cupon.get("cupon_id") is None:
        return "cupon_sin_id"
    if not match.get("can_confirm"):
        return "no_confirmable"
    if not match.get("amount_matches") or match.get("requires_rounding_writeoff"):
        return "importe_no_exacto"
    if not match.get("currency_matches"):
        return "moneda_distinta"
    try:
        if float(cupon.get("importe")) <= 0:
            return "importe_no_positivo"
    except (TypeError, ValueError):
        return "importe_invalido"
    if invoice.get("payment_state") != "not_paid":
        return "factura_con_pagos_previos"
    if not _same_amount(invoice.get("amount_residual"), invoice.get("amount_total")):
        return "factura_con_saldo_parcial"
    if not _same_amount(invoice.get("amount_residual"), cupon.get("importe")):
        return "importe_distinto_al_saldo"
    if not match.get("suggested_journal_id"):
        return "sin_diario_mapeado"
    number = _invoice_number(cupon.get("numero_factura"))
    if invoice_number_counts.get(number, 0) != 1:
        return "numero_de_factura_repetido_en_cupones"
    return ""


def find_deterministic_matches(proposal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filtra de una propuesta de conciliacion las coincidencias inequivocas."""
    invoice_number_counts: Dict[str, int] = {}
    for bucket in ("matches_unicos", "ambiguos", "sin_match"):
        for row in proposal.get(bucket, []) or []:
            number = _invoice_number((row.get("cupon") or {}).get("numero_factura"))
            if number:
                invoice_number_counts[number] = invoice_number_counts.get(number, 0) + 1
    return [
        match
        for match in proposal.get("matches_unicos", []) or []
        if not deterministic_rejection_reason(match, invoice_number_counts)
    ]
