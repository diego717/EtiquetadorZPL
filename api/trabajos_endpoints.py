"""
Trabajos de produccion: hoja TRABAJOS de las planillas configuradas. Se lee todo,
se escribe solo el estado (columna I) de un trabajo, y se imprimen la etiqueta de
orden, la orden de fabricacion y las etiquetas precargadas de Drive.

Cada endpoint recibe ?sheet=<id> para elegir la planilla (sin eso, la primera).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import trabajos_print
from trabajos_sheet import TrabajosSheet, trabajos_sheets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trabajos", tags=["trabajos"])


class TrabajoStateRequest(BaseModel):
    row: int = Field(ge=1)
    order: str = Field(min_length=1, max_length=80)
    product: str = Field(default="", max_length=500)
    state: str = Field(min_length=1, max_length=40)


class JobRef(BaseModel):
    row: int = Field(ge=1)
    order: str = Field(min_length=1, max_length=80)
    product: str = Field(default="", max_length=500)


class OrderLabelsRequest(BaseModel):
    items: List[JobRef] = Field(min_length=1, max_length=50)
    copies: int = Field(default=1, ge=1, le=trabajos_print.MAX_COPIES)
    preview: bool = False


class WorkOrderRequest(BaseModel):
    items: List[JobRef] = Field(min_length=1, max_length=20)
    pack_qty: str = Field(default="0", max_length=20)
    extra_text: str = Field(default="", max_length=2000)
    images: List[str] = Field(default_factory=list, max_length=trabajos_print.MAX_IMAGES)
    copies: int = Field(default=1, ge=1, le=trabajos_print.MAX_COPIES)
    preview: bool = False


class PreloadedPrintRequest(BaseModel):
    target: str = Field(default="label", pattern="^(label|sheet)$")
    copies: int = Field(default=1, ge=1, le=trabajos_print.MAX_COPIES)


PRELOADED_LIST_TTL_SECONDS = 300
# Lista de precargadas por planilla: {sheet_id: (momento, items)}.
_preloaded_cache: Dict[str, Any] = {}


def _sheet(sheet_id: str) -> TrabajosSheet:
    try:
        return trabajos_sheets.get(sheet_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0]))
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


def _printers(sheet: TrabajosSheet) -> Dict[str, str]:
    try:
        return sheet.printers()
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


def _resolve_jobs(sheet: TrabajosSheet, refs: List[JobRef]) -> List[Dict[str, Any]]:
    """Los datos impresos salen de la planilla, no del celular: se buscan por fila y orden."""
    try:
        items = sheet.get().get("items") or []
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))
    jobs = []
    for ref in refs:
        order = ref.order.strip()
        product = ref.product.strip()
        job = next((i for i in items if i.get("row") == ref.row and i.get("order") == order), None)
        if job is None:
            # La hoja se reordena: si la fila cambio, se busca por orden y producto.
            matches = [i for i in items if i.get("order") == order and i.get("product") == product]
            job = matches[0] if len(matches) == 1 else None
        if job is None:
            raise HTTPException(status_code=409, detail=f"No se encontro la orden {order}: actualiza la lista")
        jobs.append(job)
    return jobs


def _preview_response(result: Dict[str, Any]) -> Response:
    return Response(content=result["preview"], media_type=result["content_type"],
                    headers={"Cache-Control": "no-store"})


def _actor(request: Request, authorization: str) -> str:
    """Usuario de la app si entro con login (desde afuera); si no, la IP de la red local."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        try:
            from cloud_auth import cloud_auth_service

            payload = cloud_auth_service.verify_token(token.strip())
            if payload and payload.get("sub"):
                return str(payload["sub"])
        except Exception:
            pass
    host = request.client.host if request.client else ""
    return f"red local {host}".strip()


@router.get("/sheets")
async def list_sheets() -> Dict[str, Any]:
    try:
        return {"items": trabajos_sheets.list()}
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.get("")
async def get_trabajos(refresh: bool = False, sheet: str = "") -> Dict[str, Any]:
    target = _sheet(sheet)
    try:
        return {**await asyncio.to_thread(target.get, refresh), "sheet": target.sheet_id}
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.post("/state")
async def set_trabajo_state(
    body: TrabajoStateRequest, request: Request, sheet: str = "", authorization: str = Header(default="")
) -> Dict[str, Any]:
    target = _sheet(sheet)
    actor = _actor(request, authorization)
    try:
        return await asyncio.to_thread(
            target.set_state, body.row, body.order.strip(), body.product.strip(), body.state.strip(), actor
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.get("/state/history")
async def get_state_history(limit: int = 100, sheet: str = "") -> Dict[str, Any]:
    return {"items": _sheet(sheet).state_log(max(1, min(limit, 1000)))}


@router.post("/print/order-labels")
async def print_order_labels(body: OrderLabelsRequest, request: Request, sheet: str = "",
                             authorization: str = Header(default="")):
    target = _sheet(sheet)
    jobs = await asyncio.to_thread(_resolve_jobs, target, body.items)
    printer = _printers(target).get("label", "")
    try:
        result = await asyncio.to_thread(trabajos_print.print_order_labels, jobs, body.copies, body.preview, printer)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))
    if body.preview:
        return _preview_response(result)
    logger.info("Etiquetas de orden %s (%s) impresas por %s", [j["order"] for j in jobs], target.sheet_id,
                _actor(request, authorization))
    return result


@router.post("/print/work-order")
async def print_work_order(body: WorkOrderRequest, request: Request, sheet: str = "",
                           authorization: str = Header(default="")):
    target = _sheet(sheet)
    jobs = await asyncio.to_thread(_resolve_jobs, target, body.items)
    printer = _printers(target).get("order", "")
    try:
        result = await asyncio.to_thread(
            trabajos_print.print_work_orders, jobs, body.pack_qty, body.extra_text, body.images,
            body.copies, body.preview, printer,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))
    if body.preview:
        return _preview_response(result)
    logger.info("Ordenes de fabricacion %s (%s) impresas por %s", [j["order"] for j in jobs], target.sheet_id,
                _actor(request, authorization))
    return result


@router.get("/preloaded")
async def list_preloaded(refresh: bool = False, sheet: str = "") -> Dict[str, Any]:
    target = _sheet(sheet)
    cached = _preloaded_cache.get(target.sheet_id)
    if refresh or not cached or time.monotonic() - cached[0] >= PRELOADED_LIST_TTL_SECONDS:
        try:
            cached = (time.monotonic(), await asyncio.to_thread(target.list_preloaded))
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error))
        _preloaded_cache[target.sheet_id] = cached
    return {"items": cached[1]}


@router.get("/preloaded/{file_id}/pdf")
async def get_preloaded_pdf(file_id: str, sheet: str = "") -> Response:
    target = _sheet(sheet)
    try:
        data = await asyncio.to_thread(target.get_preloaded_pdf, file_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))
    return Response(content=data["pdf"], media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.post("/preloaded/{file_id}/print")
async def print_preloaded(file_id: str, body: PreloadedPrintRequest, request: Request, sheet: str = "",
                          authorization: str = Header(default="")) -> Dict[str, Any]:
    target = _sheet(sheet)
    printers = _printers(target)
    try:
        data = await asyncio.to_thread(target.get_preloaded_pdf, file_id)
        result = await asyncio.to_thread(
            trabajos_print.print_preloaded_pdf, data["pdf"], data["name"], body.target, body.copies, printers
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))
    logger.info("Etiqueta precargada %s (%s) impresa por %s", data["name"], target.sheet_id,
                _actor(request, authorization))
    return result


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return {"configured": trabajos_sheets.is_configured()}
