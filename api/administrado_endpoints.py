"""
Endpoints para integracion con Administrado.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from administrado_integration import administrado_integration
from odoo_integration import odoo_integration
from print_fallbacks import download_and_print_label_with_fallback, download_and_print_order_with_fallback

router = APIRouter(prefix="/api/administrado", tags=["administrado"])
logger = logging.getLogger(__name__)
PRINT_STATE_LOCK = threading.Lock()
MAX_PRINT_HISTORY_ITEMS = 500
PRINT_STATE_CACHE: Optional[Dict[str, Any]] = None
PRINT_STATE_CACHE_MTIME: Optional[float] = None
PRINT_STATE_CACHE_PATH: Optional[Path] = None
PRINT_INFLIGHT_LOCK = threading.Lock()
PRINT_INFLIGHT: Dict[str, Dict[str, Any]] = {}
ODOO_CANCEL_CACHE_LOCK = threading.Lock()
ODOO_CANCEL_CACHE: Dict[str, tuple[bool, float]] = {}
ODOO_CANCEL_CACHE_TTL_SECONDS = 45.0
ODOO_CANCEL_CACHE_MAX_ITEMS = 2000


def _friendly_error(error: Any) -> str:
    if isinstance(error, Exception):
        return odoo_integration.humanize_exception(error)
    return odoo_integration.humanize_exception(Exception(str(error or "")))


class AdministradoConfigRequest(BaseModel):
    enabled: bool = False
    base_url: str = "https://www.administrado.net"
    sales_url: str = "https://www.administrado.net/seller/ventas3"
    cookie_header: str = ""
    default_printer: str = ""
    default_copies: int = Field(default=1, ge=1, le=10)
    auto_crop_pdf: bool = True
    pdf_render_dpi: int = Field(default=300, ge=150, le=600)
    use_raw_zpl_for_labels: bool = True


class AdministradoPrintRequest(BaseModel):
    envio_id: str
    printer: str = ""


class AdministradoShipmentPrintRequest(BaseModel):
    envio_id: str
    mode: str = Field(default="both")
    order_printer: str = ""
    label_printer: str = ""
    app_username: str = ""
    operation_id: str = Field(default="", max_length=80)


class AdministradoSyncRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)


class AdministradoCookieImportRequest(BaseModel):
    browser: str = "chrome"
    profile: str = ""


class AdministradoPlaywrightCaptureRequest(BaseModel):
    timeout_seconds: int = Field(default=600, ge=60, le=1200)


def _resolve_print_state_path() -> Path:
    try:
        from config_manager import config_manager

        return Path(config_manager.get_config_directory()) / "administrado_print_state.json"
    except Exception:
        import os

        if os.name == "nt":
            base_dir = Path(os.environ.get("APPDATA", "."))
        else:
            base_dir = Path.home() / ".config"
        config_dir = base_dir / "EtiquetadorZPL"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "administrado_print_state.json"


def _default_print_state() -> Dict[str, Any]:
    return {"shipments": {}, "history": []}


def _clone_print_state(state: Dict[str, Any]) -> Dict[str, Any]:
    shipments = state.get("shipments")
    history = state.get("history")
    return {
        "shipments": dict(shipments) if isinstance(shipments, dict) else {},
        "history": list(history) if isinstance(history, list) else [],
    }


def _get_print_state_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _set_print_state_cache(path: Path, state: Dict[str, Any], mtime: Optional[float]) -> None:
    global PRINT_STATE_CACHE, PRINT_STATE_CACHE_MTIME, PRINT_STATE_CACHE_PATH
    PRINT_STATE_CACHE = _clone_print_state(state)
    PRINT_STATE_CACHE_MTIME = mtime
    PRINT_STATE_CACHE_PATH = path


def _load_print_state() -> Dict[str, Any]:
    global PRINT_STATE_CACHE, PRINT_STATE_CACHE_MTIME, PRINT_STATE_CACHE_PATH
    path = _resolve_print_state_path()
    mtime = _get_print_state_mtime(path)
    if (
        PRINT_STATE_CACHE is not None
        and PRINT_STATE_CACHE_PATH == path
        and PRINT_STATE_CACHE_MTIME == mtime
    ):
        return _clone_print_state(PRINT_STATE_CACHE)

    if not path.exists():
        state = _default_print_state()
        _set_print_state_cache(path, state, mtime)
        return _clone_print_state(state)

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            state = _default_print_state()
            _set_print_state_cache(path, state, mtime)
            return _clone_print_state(state)
        shipments = data.get("shipments")
        history = data.get("history")
        if not isinstance(shipments, dict):
            shipments = {}
        if not isinstance(history, list):
            history = []
        state = {"shipments": shipments, "history": history}
        _set_print_state_cache(path, state, mtime)
        return _clone_print_state(state)
    except Exception:
        state = _default_print_state()
        _set_print_state_cache(path, state, mtime)
        return _clone_print_state(state)


def _save_print_state(state: Dict[str, Any]) -> None:
    path = _resolve_print_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=True)
    _set_print_state_cache(path, state, _get_print_state_mtime(path))


def _record_print_event(
    *,
    envio_id: str,
    mode: str,
    success: bool,
    app_username: str = "",
    odoo_actor: str = "",
    order_result: Optional[Dict[str, Any]] = None,
    label_result: Optional[Dict[str, Any]] = None,
    confirm_result: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    shipment_id = str(envio_id or "").strip()
    if not shipment_id:
        return {}

    timestamp = datetime.now(timezone.utc).isoformat()
    mode_text = {
        "both": "Orden + etiqueta",
        "label_only": "Solo etiqueta",
        "order_only": "Solo orden Odoo",
    }.get(mode, mode or "N/A")
    state_label = mode_text if success else f"ERROR: {mode_text}"

    event = {
        "envio_id": shipment_id,
        "mode": mode,
        "success": bool(success),
        "timestamp": timestamp,
        "state_label": state_label,
        "app_username": str(app_username or "").strip(),
        "odoo_actor": str(odoo_actor or "").strip(),
        "order_printer": ((order_result or {}).get("printer") if isinstance(order_result, dict) else None),
        "label_printer": ((label_result or {}).get("printer") if isinstance(label_result, dict) else None),
        "error": str(error or "").strip(),
    }
    if isinstance(confirm_result, dict):
        event["confirm_state_before"] = confirm_result.get("state_before")
        event["confirm_state_after"] = confirm_result.get("state_after")

    with PRINT_STATE_LOCK:
        state = _load_print_state()
        shipments = state.get("shipments") or {}
        history = state.get("history") or []

        previous = shipments.get(shipment_id) or {}
        new_entry = {
            "last_print_at": timestamp,
            "last_print_result": state_label,
            "last_mode": mode,
            "print_mode": "reimprimir" if mode == "both" and success else previous.get("print_mode", "imprimir"),
            "last_success": bool(success),
            "app_username": str(app_username or "").strip(),
            "odoo_actor": str(odoo_actor or "").strip(),
            "last_error": str(error or "").strip(),
            "last_order_printer": ((order_result or {}).get("printer") if isinstance(order_result, dict) else ""),
            "last_label_printer": ((label_result or {}).get("printer") if isinstance(label_result, dict) else ""),
            "last_confirm_state_before": (
                (confirm_result or {}).get("state_before")
                if isinstance(confirm_result, dict)
                else ""
            ),
            "last_confirm_state_after": (
                (confirm_result or {}).get("state_after")
                if isinstance(confirm_result, dict)
                else ""
            ),
        }
        shipments[shipment_id] = new_entry

        history.append(event)
        if len(history) > MAX_PRINT_HISTORY_ITEMS:
            history = history[-MAX_PRINT_HISTORY_ITEMS:]

        state["shipments"] = shipments
        state["history"] = history
        _save_print_state(state)

    return new_entry


def _merge_print_state_into_sales(sales: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    with PRINT_STATE_LOCK:
        state = _load_print_state()
    shipments = state.get("shipments") or {}
    if not isinstance(shipments, dict):
        return sales

    for sale in sales:
        envio_id = str(sale.get("envio_id") or "").strip()
        if not envio_id:
            continue
        info = shipments.get(envio_id)
        if not isinstance(info, dict):
            continue
        sale["_last_print_at"] = info.get("last_print_at")
        sale["_last_print_result"] = info.get("last_print_result")
        sale["_last_success"] = info.get("last_success")
        sale["_last_print_actor"] = info.get("odoo_actor") or info.get("app_username") or ""
        sale["_last_order_printer"] = info.get("last_order_printer") or ""
        sale["_last_label_printer"] = info.get("last_label_printer") or ""
        sale["_last_confirm_state_before"] = info.get("last_confirm_state_before") or ""
        sale["_last_confirm_state_after"] = info.get("last_confirm_state_after") or ""
        sale["_last_error"] = info.get("last_error") or ""
        # Administrado es la fuente de verdad de si la etiqueta ya se imprimio (puede haberse
        # impreso directo en la web). El historial local solo puede adelantar "reimprimir"
        # cuando se imprimio desde la app y Administrado aun no lo refleja; nunca volver atras.
        if info.get("print_mode") == "reimprimir":
            sale["print_mode"] = "reimprimir"
    return sales


def _attach_odoo_stock_statuses(sales: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Agrega disponibilidad Odoo sin convertirla en requisito para imprimir."""
    if not isinstance(sales, list):
        return []

    enabled = bool(odoo_integration.config.get("enabled")) and odoo_integration.is_configured()
    if not enabled:
        fallback = {
            "code": "unavailable",
            "label": "Odoo no configurado",
            "detail": "Configura y habilita Odoo para consultar entregas y stock.",
            "pickings": [],
        }
        for sale in sales:
            if isinstance(sale, dict):
                sale["odoo_stock"] = dict(fallback)
        return sales

    envio_ids = [
        str(sale.get("envio_id") or "").strip()
        for sale in sales
        if isinstance(sale, dict) and str(sale.get("envio_id") or "").strip()
    ]
    try:
        statuses = odoo_integration.get_sale_order_stock_statuses(envio_ids)
    except Exception as exc:
        message = _friendly_error(exc)
        logger.warning("No se pudo consultar stock Odoo en bloque: %s", message)
        statuses = {}
        fallback = {
            "code": "error",
            "label": "Stock no disponible",
            "detail": message,
            "pickings": [],
        }
    else:
        fallback = {
            "code": "unknown",
            "label": "Stock sin datos",
            "detail": "Odoo no devolvio informacion para este envio.",
            "pickings": [],
        }

    for sale in sales:
        if not isinstance(sale, dict):
            continue
        envio_id = str(sale.get("envio_id") or "").strip()
        sale["odoo_stock"] = statuses.get(envio_id, dict(fallback))
    return sales


def _looks_cancelled_in_administrado(sale: Dict[str, Any]) -> bool:
    haystack = " ".join(
        str(sale.get(key) or "").strip().lower()
        for key in ("shipping_status", "shipping_substatus", "context_text", "status", "state")
    )
    if not haystack:
        return False
    cancelled_tokens = (
        "cancelad",
        "cancelado",
        "cancelada",
        "cancelacion",
        "anulad",
        "anulado",
        "anulada",
        "anulacion",
        "canceled",
        "cancelled",
    )
    return any(token in haystack for token in cancelled_tokens)


def _prune_odoo_cancel_cache_locked(now: float) -> None:
    expired_keys = [envio_id for envio_id, (_, expires_at) in ODOO_CANCEL_CACHE.items() if expires_at <= now]
    for envio_id in expired_keys:
        ODOO_CANCEL_CACHE.pop(envio_id, None)

    if len(ODOO_CANCEL_CACHE) <= ODOO_CANCEL_CACHE_MAX_ITEMS:
        return

    ordered_items = sorted(ODOO_CANCEL_CACHE.items(), key=lambda item: item[1][1])
    overflow = len(ODOO_CANCEL_CACHE) - ODOO_CANCEL_CACHE_MAX_ITEMS
    for envio_id, _ in ordered_items[:overflow]:
        ODOO_CANCEL_CACHE.pop(envio_id, None)


def _get_cancelled_envio_ids_in_odoo(envio_ids: list[str]) -> set[str]:
    normalized: list[str] = []
    seen = set()
    for raw_envio in envio_ids or []:
        envio = str(raw_envio or "").strip()
        if not envio or envio in seen:
            continue
        normalized.append(envio)
        seen.add(envio)

    if not normalized:
        return set()

    cached_cancelled: set[str] = set()
    pending: list[str] = []
    now = time.monotonic()

    with ODOO_CANCEL_CACHE_LOCK:
        _prune_odoo_cancel_cache_locked(now)
        for envio in normalized:
            cached = ODOO_CANCEL_CACHE.get(envio)
            if cached is None:
                pending.append(envio)
                continue
            is_cancelled, expires_at = cached
            if expires_at <= now:
                ODOO_CANCEL_CACHE.pop(envio, None)
                pending.append(envio)
                continue
            if is_cancelled:
                cached_cancelled.add(envio)

    remote_cancelled: set[str] = set()
    if pending:
        remote_cancelled = odoo_integration.get_cancelled_envio_ids(pending)
        expires_at = time.monotonic() + ODOO_CANCEL_CACHE_TTL_SECONDS
        with ODOO_CANCEL_CACHE_LOCK:
            for envio in pending:
                ODOO_CANCEL_CACHE[envio] = (envio in remote_cancelled, expires_at)
            _prune_odoo_cancel_cache_locked(time.monotonic())

    return cached_cancelled.union(remote_cancelled)


def _is_cancelled_in_odoo(envio_id: str) -> bool:
    try:
        normalized_envio = str(envio_id or "").strip()
        if not normalized_envio:
            return False
        cancelled_ids = _get_cancelled_envio_ids_in_odoo([normalized_envio])
    except Exception as exc:
        logger.warning("No se pudo validar estado Odoo para envio %s: %s", envio_id, exc)
        return False
    return normalized_envio in cancelled_ids


def _filter_non_printable_sales(sales: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    if not isinstance(sales, list):
        return []

    check_odoo_cancel = bool(odoo_integration.config.get("enabled")) and odoo_integration.is_configured()
    cancelled_in_odoo: set[str] = set()
    if check_odoo_cancel:
        envio_ids = [
            str(sale.get("envio_id") or "").strip()
            for sale in sales
            if isinstance(sale, dict) and str(sale.get("envio_id") or "").strip()
        ]
        if envio_ids:
            try:
                cancelled_in_odoo = _get_cancelled_envio_ids_in_odoo(envio_ids)
            except Exception as exc:
                logger.warning("No se pudo consultar cancelaciones Odoo en bloque: %s", exc)
                cancelled_in_odoo = set()

    filtered: list[Dict[str, Any]] = []

    for sale in sales:
        if not isinstance(sale, dict):
            continue

        if _looks_cancelled_in_administrado(sale):
            continue

        envio_id = str(sale.get("envio_id") or "").strip()
        if check_odoo_cancel and envio_id and envio_id in cancelled_in_odoo:
            continue

        filtered.append(sale)

    return filtered


def _register_print_inflight(envio_id: str, mode: str, app_username: str) -> None:
    key = str(envio_id or "").strip()
    if not key:
        return
    now = time.time()
    with PRINT_INFLIGHT_LOCK:
        current = PRINT_INFLIGHT.get(key)
        if current:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"El envio {key} ya se esta procesando "
                    f"(usuario={current.get('app_username', '-')}, mode={current.get('mode', '-')}). "
                    "Espera unos segundos y reintenta."
                ),
            )
        PRINT_INFLIGHT[key] = {
            "started_at": now,
            "mode": str(mode or ""),
            "app_username": str(app_username or ""),
        }


def _release_print_inflight(envio_id: str) -> None:
    key = str(envio_id or "").strip()
    if not key:
        return
    with PRINT_INFLIGHT_LOCK:
        PRINT_INFLIGHT.pop(key, None)


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return administrado_integration.get_public_config()


@router.post("/config")
async def save_config(config: AdministradoConfigRequest) -> Dict[str, Any]:
    payload = config.dict()
    if not payload.get("cookie_header"):
        payload.pop("cookie_header", None)
    return administrado_integration.save_config(payload)


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return administrado_integration.get_public_config()


@router.post("/session/test")
async def test_session() -> Dict[str, Any]:
    try:
        return await administrado_integration.test_session_async()
    except Exception as exc:
        message = _friendly_error(exc)
        administrado_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/session/refresh")
async def refresh_playwright_session(timeout_seconds: int = 60) -> Dict[str, Any]:
    try:
        result = await administrado_integration.refresh_playwright_session_async(
            timeout_seconds,
        )
        return result
    except Exception as exc:
        message = _friendly_error(exc)
        administrado_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/cookies/import")
async def import_cookies(request: AdministradoCookieImportRequest) -> Dict[str, Any]:
    try:
        return administrado_integration.import_browser_cookies(
            browser=request.browser,
            profile=request.profile,
        )
    except Exception as exc:
        message = _friendly_error(exc)
        administrado_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/playwright/capture-session")
async def capture_playwright_session(request: AdministradoPlaywrightCaptureRequest) -> Dict[str, Any]:
    try:
        return await administrado_integration.capture_playwright_session_async(
            request.timeout_seconds,
        )
    except Exception as exc:
        message = _friendly_error(exc)
        administrado_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/sales/sync")
async def sync_sales(request: AdministradoSyncRequest) -> Dict[str, Any]:
    try:
        sales = await asyncio.to_thread(
            administrado_integration.list_label_links,
            request.limit,
        )
        sales = await asyncio.to_thread(_filter_non_printable_sales, sales)
        sales = _merge_print_state_into_sales(sales)
        sales = await asyncio.to_thread(_attach_odoo_stock_statuses, sales)
        return {"sales": sales, "count": len(sales)}
    except Exception as exc:
        message = _friendly_error(exc)
        administrado_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/labels/print")
async def print_label(request: AdministradoPrintRequest) -> Dict[str, Any]:
    try:
        pdf_bytes = await asyncio.to_thread(
            administrado_integration.download_label_pdf,
            request.envio_id,
        )
        result = await asyncio.to_thread(
            administrado_integration.process_downloaded_pdf,
            pdf_bytes,
            request.envio_id,
            request.printer,
        )
        _record_print_event(
            envio_id=request.envio_id,
            mode="label_only",
            success=bool(result.get("success")),
            label_result=result,
            error="" if result.get("success") else str(result.get("error") or ""),
        )
        return result
    except Exception as exc:
        message = _friendly_error(exc)
        _record_print_event(
            envio_id=request.envio_id,
            mode="label_only",
            success=False,
            error=message,
        )
        administrado_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


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


def _normalize_shipment_print_mode(mode_raw: Any) -> str:
    mode = str(mode_raw or "both").strip().lower()
    mode = mode.replace("-", "_").replace(" ", "_")
    mode_aliases = {
        "orderonly": "order_only",
        "only_order": "order_only",
        "order": "order_only",
        "labelonly": "label_only",
        "only_label": "label_only",
        "label": "label_only",
    }
    mode = mode_aliases.get(mode, mode)
    if mode not in {"both", "label_only", "order_only"}:
        raise ValueError("mode invalido. Usa 'both', 'label_only' o 'order_only'")
    return mode


def _print_order_with_fallback(
    envio_id: str,
    order_id: int,
    preferred_printer: str = "",
    auth_override: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    return download_and_print_order_with_fallback(
        envio_id=envio_id,
        order_id=order_id,
        preferred_printer=preferred_printer,
        auth_override=auth_override,
        report_name=str(odoo_integration.config.get("report_name", "")).strip(),
    )


def _print_label_with_fallback(envio_id: str, preferred_printer: str = "") -> Dict[str, Any]:
    return download_and_print_label_with_fallback(
        envio_id=envio_id,
        preferred_printer=preferred_printer,
        copies=_safe_int(odoo_integration.config.get("default_label_copies", 1)),
    )


@router.post("/shipments/print")
async def print_shipment(
    request: AdministradoShipmentPrintRequest,
) -> Dict[str, Any]:
    try:
        envio_id = str(request.envio_id or "").strip()
        if not envio_id:
            raise ValueError("envio_id vacio")

        mode = _normalize_shipment_print_mode(request.mode)
        app_username = str(request.app_username or "").strip()

        def _executor() -> Dict[str, Any]:
            _register_print_inflight(envio_id, mode, app_username)
            try:
                auth_override = odoo_integration.resolve_operator_auth(app_username)
                active_odoo_user = (
                    str(auth_override.get("username", "")).strip()
                    if auth_override
                    else str(odoo_integration.config.get("username", "")).strip()
                )

                order = None
                order_result = None
                confirm_result = None
                if mode in {"both", "order_only"}:
                    order = odoo_integration.find_sale_order_by_envio(envio_id, auth_override)
                    if not order:
                        raise ValueError(
                            f"No se encontro orden Odoo para envio {envio_id}. Revisa campo shipment/report_name."
                        )

                    if bool(odoo_integration.config.get("confirm_order_on_print")):
                        confirm_result = odoo_integration.confirm_sale_order(int(order["id"]), auth_override)

                    order_result = _print_order_with_fallback(
                        envio_id,
                        int(order["id"]),
                        request.order_printer,
                        auth_override,
                    )
                    if not order_result.get("success"):
                        raise ValueError(
                            f"No se pudo imprimir orden Odoo para envio {envio_id}: {order_result.get('error', 'sin detalle')}"
                        )

                    if mode == "both":
                        delay_seconds = _safe_int(
                            odoo_integration.config.get("automation_order_to_label_delay_seconds", 1),
                            default=1,
                            min_value=0,
                            max_value=30,
                        )
                        if delay_seconds > 0:
                            time.sleep(delay_seconds)

                label_result = None
                if mode in {"both", "label_only"}:
                    label_result = _print_label_with_fallback(
                        envio_id,
                        request.label_printer,
                    )
                    if not label_result.get("success"):
                        raise ValueError(
                            f"No se pudo imprimir etiqueta para envio {envio_id}: {label_result.get('error', 'sin detalle')}"
                        )

                odoo_note_result = None
                if order and mode in {"both", "order_only"}:
                    try:
                        odoo_note_result = odoo_integration.post_sale_order_print_note(
                            order_id=int(order["id"]),
                            envio_id=envio_id,
                            mode=mode,
                            order_printer=str((order_result or {}).get("printer") or ""),
                            label_printer=str((label_result or {}).get("printer") or ""),
                            event_key=str(request.operation_id or ""),
                            auth_override=auth_override,
                        )
                    except Exception as exc:
                        note_error = _friendly_error(exc)
                        logger.warning(
                            "Impresion correcta, pero no se pudo registrar nota Odoo para envio %s: %s",
                            envio_id,
                            note_error,
                        )
                        odoo_note_result = {
                            "success": False,
                            "error": note_error,
                        }

                _record_print_event(
                    envio_id=envio_id,
                    mode=mode,
                    success=True,
                    app_username=app_username,
                    odoo_actor=active_odoo_user,
                    order_result=order_result,
                    label_result=label_result,
                    confirm_result=confirm_result,
                )
                return {
                    "success": True,
                    "envio_id": envio_id,
                    "mode": mode,
                    "app_username": app_username or None,
                    "odoo_actor": active_odoo_user or None,
                    "confirm_result": confirm_result,
                    "order_result": order_result,
                    "label_result": label_result,
                    "odoo_note_result": odoo_note_result,
                }
            finally:
                _release_print_inflight(envio_id)

        return await asyncio.to_thread(_executor)
    except HTTPException:
        raise
    except Exception as exc:
        message = _friendly_error(exc)
        mode_for_event = str(request.mode or "both")
        app_username_for_event = str(locals().get("app_username") or request.app_username or "")
        try:
            mode_for_event = _normalize_shipment_print_mode(mode_for_event)
        except Exception:
            pass
        _record_print_event(
            envio_id=str(request.envio_id or ""),
            mode=mode_for_event,
            success=False,
            app_username=app_username_for_event,
            error=message,
        )
        administrado_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.get("/prints/history")
async def get_print_history(limit: int = 50) -> Dict[str, Any]:
    safe_limit = _safe_int(limit, default=50, min_value=1, max_value=200)
    with PRINT_STATE_LOCK:
        state = _load_print_state()
    history = state.get("history") or []
    if not isinstance(history, list):
        history = []
    return {
        "count": len(history),
        "items": history[-safe_limit:],
        "state_path": str(_resolve_print_state_path()),
    }
