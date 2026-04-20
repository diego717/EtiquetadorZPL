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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from administrado_integration import administrado_integration
from auth_dependencies import get_optional_current_user
from odoo_integration import odoo_integration
from print_fallbacks import download_and_print_label_with_fallback, download_and_print_order_with_fallback
from print_dispatch_queue import print_dispatch_queue

router = APIRouter(prefix="/api/administrado", tags=["administrado"])
logger = logging.getLogger(__name__)
PRINT_STATE_LOCK = threading.Lock()
MAX_PRINT_HISTORY_ITEMS = 500
PRINT_INFLIGHT_LOCK = threading.Lock()
PRINT_INFLIGHT: Dict[str, Dict[str, Any]] = {}
DISPATCH_MAX_ATTEMPTS = 3


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


class AdministradoPrintRequest(BaseModel):
    envio_id: str
    printer: str = ""


class AdministradoShipmentPrintRequest(BaseModel):
    envio_id: str
    mode: str = Field(default="both")
    order_printer: str = ""
    label_printer: str = ""
    app_username: str = ""


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


def _load_print_state() -> Dict[str, Any]:
    path = _resolve_print_state_path()
    if not path.exists():
        return _default_print_state()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return _default_print_state()
        shipments = data.get("shipments")
        history = data.get("history")
        if not isinstance(shipments, dict):
            shipments = {}
        if not isinstance(history, list):
            history = []
        return {"shipments": shipments, "history": history}
    except Exception:
        return _default_print_state()


def _save_print_state(state: Dict[str, Any]) -> None:
    path = _resolve_print_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=True)


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
        if info.get("print_mode"):
            sale["print_mode"] = info.get("print_mode")
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


def _is_cancelled_in_odoo(envio_id: str) -> bool:
    try:
        order = odoo_integration.find_sale_order_by_envio(envio_id, include_all_states=True)
    except Exception as exc:
        logger.warning("No se pudo validar estado Odoo para envio %s: %s", envio_id, exc)
        return False
    if not order:
        return False
    return str(order.get("state") or "").strip().lower() == "cancel"


def _filter_non_printable_sales(sales: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    if not isinstance(sales, list):
        return []

    check_odoo_cancel = bool(odoo_integration.config.get("enabled")) and odoo_integration.is_configured()
    filtered: list[Dict[str, Any]] = []

    for sale in sales:
        if not isinstance(sale, dict):
            continue

        if _looks_cancelled_in_administrado(sale):
            continue

        envio_id = str(sale.get("envio_id") or "").strip()
        if check_odoo_cancel and envio_id and _is_cancelled_in_odoo(envio_id):
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
        return await asyncio.to_thread(administrado_integration.test_session)
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
        return await asyncio.to_thread(
            administrado_integration.capture_playwright_session,
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


def _build_dispatch_task_view(task: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(task, dict):
        return None
    return {
        "id": task.get("id"),
        "status": task.get("status"),
        "attempt_count": task.get("attempt_count"),
        "max_attempts": task.get("max_attempts"),
        "last_error": task.get("last_error"),
        "updated_at": task.get("updated_at"),
        "completed_at": task.get("completed_at"),
        "next_retry_at": task.get("next_retry_at"),
        "idempotency_key": task.get("idempotency_key"),
    }


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
    user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    try:
        envio_id = str(request.envio_id or "").strip()
        if not envio_id:
            raise ValueError("envio_id vacio")

        mode = _normalize_shipment_print_mode(request.mode)
        token_username = str((user or {}).get("username") or "").strip()
        body_username = str(request.app_username or "").strip()
        app_username = token_username or body_username
        auth_source = "token" if token_username else ("body" if body_username else "none")
        app_username_key = str(app_username).strip().lower() or "anon"
        idempotency_key = f"administrado:{envio_id}:{mode}:{app_username_key}"
        dispatch_payload = {
            "envio_id": envio_id,
            "mode": mode,
            "order_printer": str(request.order_printer or "").strip(),
            "label_printer": str(request.label_printer or "").strip(),
            "app_username": app_username,
            "auth_source": auth_source,
        }

        def _executor() -> Dict[str, Any]:
            _register_print_inflight(envio_id, mode, app_username)
            try:
                auth_override = odoo_integration.resolve_operator_auth(app_username)
                confirm_on_print_enabled = bool(odoo_integration.config.get("confirm_order_on_print"))
                requires_order_flow = mode in {"both", "order_only"}

                if confirm_on_print_enabled and requires_order_flow:
                    if not app_username:
                        raise ValueError(
                            "Falta usuario operador. Inicia sesion para confirmar en Odoo."
                        )
                    if auth_source != "token":
                        raise ValueError(
                            "La confirmacion Odoo requiere sesion autenticada. "
                            "Inicia sesion del operador (token/cookie) y reintenta."
                        )
                    if not auth_override:
                        raise ValueError(
                            "No hay usuario Odoo configurado para el operador "
                            f"'{app_username}'. Cargalo en Odoo > Usuarios Odoo por operador."
                        )

                active_odoo_user = (
                    str(auth_override.get("username", "")).strip()
                    if auth_override
                    else str(odoo_integration.config.get("username", "")).strip()
                )

                order_result = None
                confirm_result = None
                if mode in {"both", "order_only"}:
                    order = odoo_integration.find_sale_order_by_envio(envio_id, auth_override)
                    if not order:
                        raise ValueError(
                            f"No se encontro orden Odoo para envio {envio_id}. Revisa campo shipment/report_name."
                        )

                    if confirm_on_print_enabled:
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
                    "auth_source": auth_source,
                    "odoo_actor": active_odoo_user or None,
                    "confirm_result": confirm_result,
                    "order_result": order_result,
                    "label_result": label_result,
                }
            finally:
                _release_print_inflight(envio_id)

        outcome = await asyncio.to_thread(
            print_dispatch_queue.execute_with_idempotency,
            source="administrado",
            entity_id=envio_id,
            action=mode,
            idempotency_key=idempotency_key,
            request_payload=dispatch_payload,
            executor=_executor,
            max_attempts=DISPATCH_MAX_ATTEMPTS,
        )

        if outcome.get("status") == "processing":
            task_view = _build_dispatch_task_view(outcome.get("task"))
            raise HTTPException(
                status_code=409,
                detail=f"El envio {envio_id} ya se esta procesando. task={task_view.get('id') if task_view else '-'}",
            )

        if outcome.get("status") == "completed":
            result = outcome.get("result") or {}
            if not isinstance(result, dict):
                result = {
                    "success": True,
                    "envio_id": envio_id,
                    "mode": mode,
                    "result": result,
                }
            result["dispatch_task"] = _build_dispatch_task_view(outcome.get("task"))
            result["idempotent_reused"] = bool(outcome.get("reused"))
            return result

        message = _friendly_error(outcome.get("error") or "No se pudo completar el despacho de impresion.")
        if not outcome.get("reused"):
            _record_print_event(
                envio_id=envio_id,
                mode=mode,
                success=False,
                app_username=app_username,
                error=message,
            )
        administrado_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)
    except HTTPException:
        raise
    except Exception as exc:
        message = _friendly_error(exc)
        mode_for_event = str(request.mode or "both")
        effective_app_username = str(locals().get("app_username") or request.app_username or "")
        try:
            mode_for_event = _normalize_shipment_print_mode(mode_for_event)
        except Exception:
            pass
        _record_print_event(
            envio_id=str(request.envio_id or ""),
            mode=mode_for_event,
            success=False,
            app_username=effective_app_username,
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
