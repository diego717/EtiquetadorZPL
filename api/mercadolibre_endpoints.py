"""
Endpoints para integracion con Mercado Libre.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from mercadolibre_integration import mercadolibre_integration
from print_dispatch_queue import print_dispatch_queue

logger = logging.getLogger(__name__)
DISPATCH_MAX_ATTEMPTS = 3

router = APIRouter(prefix="/api/mercadolibre", tags=["mercadolibre"])


class MercadoLibreConfigRequest(BaseModel):
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8002/api/mercadolibre/oauth/callback"
    default_printer: str = ""
    default_copies: int = Field(default=1, ge=1, le=10)
    auto_print: bool = False
    response_type: str = "zpl2"


class PrintShipmentRequest(BaseModel):
    shipment_id: str
    printer: str = ""
    copies: int = Field(default=1, ge=1, le=10)
    response_type: str = "zpl2"


class SyncSalesRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)


def _read_api_port() -> str:
    port_file = Path("api_port.txt")
    if port_file.exists():
        port = port_file.read_text(encoding="utf-8").strip()
        if port:
            return port
    return "8002"


def _dispatch_to_local_print(filename: str, content: str, printer: str, copies: int) -> Dict[str, Any]:
    selected_printer = printer.strip() or mercadolibre_integration.get_default_printer()
    if not selected_printer:
        raise HTTPException(status_code=400, detail="No hay impresora configurada para Mercado Libre")

    payload = {
        "filename": filename,
        "content": content,
        "printer": selected_printer,
        "copies": copies,
    }
    port = _read_api_port()
    response = requests.post(
        f"http://localhost:{port}/api/process-file",
        json=payload,
        timeout=20,
    )
    response.raise_for_status()
    result = response.json()
    result["printer"] = selected_printer
    return result


def _print_shipment_label(shipment_id: str, printer: str = "", copies: Optional[int] = None, response_type: str = "zpl2") -> Dict[str, Any]:
    shipment = mercadolibre_integration.get_shipment(shipment_id)
    if not mercadolibre_integration.shipment_ready_to_print(shipment):
        raise HTTPException(
            status_code=409,
            detail=(
                f"El shipment {shipment_id} no esta listo para imprimir. "
                f"status={shipment.get('status')} substatus={shipment.get('substatus')}"
            ),
        )

    raw_label = mercadolibre_integration.download_shipment_label([shipment_id], response_type=response_type)
    zpl_content = mercadolibre_integration.extract_zpl_from_label_payload(raw_label, response_type=response_type)
    selected_copies = copies or mercadolibre_integration.get_default_copies()
    dispatch = _dispatch_to_local_print(
        filename=f"meli_{shipment_id}.zpl",
        content=zpl_content,
        printer=printer,
        copies=selected_copies,
    )

    return {
        "shipment_id": shipment_id,
        "shipment_status": shipment.get("status"),
        "shipment_substatus": shipment.get("substatus"),
        "print_job": dispatch,
    }


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


async def _print_shipment_with_queue(
    *,
    shipment_id: str,
    printer: str = "",
    copies: Optional[int] = None,
    response_type: str = "zpl2",
    source_context: str = "manual",
) -> Dict[str, Any]:
    safe_shipment_id = str(shipment_id or "").strip()
    if not safe_shipment_id:
        raise HTTPException(status_code=400, detail="shipment_id vacio")

    idempotency_key = f"mercadolibre:{safe_shipment_id}:label"
    payload = {
        "shipment_id": safe_shipment_id,
        "printer": str(printer or "").strip(),
        "copies": int(copies or mercadolibre_integration.get_default_copies()),
        "response_type": response_type,
        "source_context": source_context,
    }

    def _executor() -> Dict[str, Any]:
        return _print_shipment_label(
            shipment_id=safe_shipment_id,
            printer=printer,
            copies=copies,
            response_type=response_type,
        )

    outcome = await asyncio.to_thread(
        print_dispatch_queue.execute_with_idempotency,
        source="mercadolibre",
        entity_id=safe_shipment_id,
        action="label_only",
        idempotency_key=idempotency_key,
        request_payload=payload,
        executor=_executor,
        max_attempts=DISPATCH_MAX_ATTEMPTS,
    )

    status = outcome.get("status")
    if status == "processing":
        task_view = _build_dispatch_task_view(outcome.get("task"))
        raise HTTPException(
            status_code=409,
            detail=(
                f"El shipment {safe_shipment_id} ya se esta procesando. "
                f"task={task_view.get('id') if task_view else '-'}"
            ),
        )

    if status == "completed":
        result = outcome.get("result") or {}
        if not isinstance(result, dict):
            result = {"shipment_id": safe_shipment_id, "result": result}
        result["dispatch_task"] = _build_dispatch_task_view(outcome.get("task"))
        result["idempotent_reused"] = bool(outcome.get("reused"))
        return result

    error_message = str(outcome.get("error") or "No se pudo completar la impresion del shipment.")
    raise HTTPException(status_code=500, detail=error_message)


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return mercadolibre_integration.get_public_config()


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return mercadolibre_integration.get_public_config()


@router.post("/config")
async def save_config(config: MercadoLibreConfigRequest) -> Dict[str, Any]:
    if config.response_type != "zpl2":
        raise HTTPException(status_code=400, detail="Por ahora solo se soporta response_type=zpl2")
    payload = config.dict()
    if not payload.get("client_secret"):
        payload.pop("client_secret", None)
    return mercadolibre_integration.save_config(payload)


@router.get("/auth-url")
async def get_auth_url(state: str = Query(default="etiquetadorzpl")) -> Dict[str, Any]:
    try:
        url = mercadolibre_integration.build_auth_url(state=state)
        return {"auth_url": url}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/oauth/callback")
async def oauth_callback(code: str, state: Optional[str] = None) -> Dict[str, Any]:
    try:
        config = mercadolibre_integration.exchange_code(code)
        return {
            "success": True,
            "state": state,
            "config": config,
        }
    except Exception as exc:
        mercadolibre_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=400, detail=f"Error completando OAuth: {exc}")


@router.post("/oauth/refresh")
async def refresh_oauth_token() -> Dict[str, Any]:
    try:
        return mercadolibre_integration.refresh_access_token()
    except Exception as exc:
        mercadolibre_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/shipments/print")
async def print_shipment(request: PrintShipmentRequest) -> Dict[str, Any]:
    try:
        return await _print_shipment_with_queue(
            shipment_id=request.shipment_id,
            printer=request.printer,
            copies=request.copies,
            response_type=request.response_type,
            source_context="manual",
        )
    except HTTPException:
        raise
    except Exception as exc:
        mercadolibre_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sales/sync")
async def sync_ready_sales(request: SyncSalesRequest) -> Dict[str, Any]:
    try:
        sales = mercadolibre_integration.list_ready_to_print_sales(limit=request.limit)
        ready_count = sum(1 for sale in sales if sale.get("ready_to_print"))
        return {
            "sales": sales,
            "count": len(sales),
            "ready_count": ready_count,
        }
    except Exception as exc:
        mercadolibre_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/shipments/{shipment_id}")
async def get_shipment(shipment_id: str) -> Dict[str, Any]:
    try:
        return mercadolibre_integration.get_shipment(shipment_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/webhook")
async def receive_webhook(request: Request) -> Dict[str, Any]:
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Webhook invalido: {exc}")

    logger.info("Webhook Mercado Libre recibido: %s", payload)

    try:
        shipment_id = mercadolibre_integration.resolve_shipment_id_from_notification(payload)
    except Exception as exc:
        mercadolibre_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=400, detail=f"No se pudo resolver shipment desde notificacion: {exc}")

    if not shipment_id:
        return {
            "accepted": True,
            "auto_print": False,
            "message": "Notificacion recibida, pero sin shipment utilizable",
        }

    auto_print = bool(mercadolibre_integration.config.get("auto_print"))
    if not auto_print:
        return {
            "accepted": True,
            "auto_print": False,
            "shipment_id": shipment_id,
        }

    try:
        result = await _print_shipment_with_queue(
            shipment_id=shipment_id,
            source_context="webhook",
        )
        return {
            "accepted": True,
            "auto_print": True,
            "result": result,
        }
    except HTTPException as exc:
        mercadolibre_integration.save_config({"last_error": str(exc.detail)})
        return {
            "accepted": True,
            "auto_print": True,
            "shipment_id": shipment_id,
            "error": exc.detail,
        }
    except Exception as exc:
        mercadolibre_integration.save_config({"last_error": str(exc)})
        return {
            "accepted": True,
            "auto_print": True,
            "shipment_id": shipment_id,
            "error": str(exc),
        }
