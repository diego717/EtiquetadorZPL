"""
Cloud print queue endpoints.
These endpoints are separated from legacy local-print routes.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from administrado_integration import administrado_integration
from auth_dependencies import require_admin, require_agent_or_admin
from cloud_queue import cloud_print_queue

router = APIRouter(prefix="/api/cloud", tags=["cloud"])


class QueueAdministradoRequest(BaseModel):
    envio_id: str
    printer_hint: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ClaimTaskRequest(BaseModel):
    agent_id: str
    printers: List[str] = Field(default_factory=list)


class CompleteTaskRequest(BaseModel):
    success: bool
    result_message: str = ""
    error_message: str = ""


class EnqueuePdfTaskRequest(BaseModel):
    source: str = "manual"
    shipment_id: str
    pdf_base64: str
    printer_hint: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.post("/administrado/queue")
async def queue_administrado_label(
    request: QueueAdministradoRequest,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    envio_id = request.envio_id.strip()
    if not envio_id:
        raise HTTPException(status_code=400, detail="envio_id es obligatorio")
    try:
        pdf_bytes = await asyncio.to_thread(administrado_integration.download_label_pdf, envio_id)
        task = await asyncio.to_thread(
            cloud_print_queue.enqueue_pdf_task,
            "administrado",
            envio_id,
            pdf_bytes,
            user.get("username", "unknown"),
            request.printer_hint,
            request.metadata,
        )
        return {
            "queued": True,
            "task": task,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo encolar etiqueta: {exc}")


@router.get("/tasks")
async def list_cloud_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None),
    _: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    tasks = await asyncio.to_thread(cloud_print_queue.list_tasks, limit, status)
    return {"tasks": tasks, "count": len(tasks)}


@router.post("/tasks/enqueue-pdf")
async def enqueue_pdf_task(
    request: EnqueuePdfTaskRequest,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    shipment_id = request.shipment_id.strip()
    if not shipment_id:
        raise HTTPException(status_code=400, detail="shipment_id es obligatorio")
    try:
        pdf_bytes = base64.b64decode(request.pdf_base64.encode("ascii"))
    except Exception:
        raise HTTPException(status_code=400, detail="pdf_base64 invalido")
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="El contenido no parece un PDF valido")

    task = await asyncio.to_thread(
        cloud_print_queue.enqueue_pdf_task,
        request.source.strip() or "manual",
        shipment_id,
        pdf_bytes,
        user.get("username", "unknown"),
        request.printer_hint,
        request.metadata,
    )
    return {"queued": True, "task": task}


@router.post("/tasks/claim")
async def claim_cloud_task(
    request: ClaimTaskRequest,
    user: Dict[str, Any] = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    fallback_agent = request.agent_id.strip()
    agent_id = (user.get("username") or fallback_agent or "").strip()
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id es obligatorio")
    task = await asyncio.to_thread(cloud_print_queue.claim_next_task, agent_id, request.printers)
    if not task:
        return {"task": None}
    return {"task": task}


@router.post("/tasks/{task_id}/complete")
async def complete_cloud_task(
    task_id: str,
    request: CompleteTaskRequest,
    user: Dict[str, Any] = Depends(require_agent_or_admin),
) -> Dict[str, Any]:
    agent_id = user.get("username", "agent")
    updated = await asyncio.to_thread(
        cloud_print_queue.complete_task,
        task_id,
        agent_id,
        request.success,
        request.result_message,
        request.error_message,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Task no encontrado o no se pudo actualizar")
    task = await asyncio.to_thread(cloud_print_queue.get_task, task_id, False)
    return {"ok": True, "task": task}
