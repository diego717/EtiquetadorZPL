"""
Endpoints de observabilidad y control de la cola de despachos de impresion.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from print_dispatch_queue import print_dispatch_queue

router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])


class RetryDispatchTaskRequest(BaseModel):
    reset_attempts: bool = True
    clear_result: bool = False


def _build_task_view(task: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(task, dict):
        return None
    return {
        "id": task.get("id"),
        "source": task.get("source"),
        "entity_id": task.get("entity_id"),
        "action": task.get("action"),
        "status": task.get("status"),
        "attempt_count": task.get("attempt_count"),
        "max_attempts": task.get("max_attempts"),
        "last_error": task.get("last_error"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "last_attempt_at": task.get("last_attempt_at"),
        "next_retry_at": task.get("next_retry_at"),
        "completed_at": task.get("completed_at"),
        "idempotency_key": task.get("idempotency_key"),
        "request_payload": task.get("request_payload"),
        "result_payload": task.get("result_payload"),
    }


@router.get("/tasks")
async def list_dispatch_tasks(
    limit: int = Query(default=50, ge=1, le=500),
    status: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    entity_id: Optional[str] = Query(default=None),
    idempotency_key: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    tasks = await asyncio.to_thread(
        print_dispatch_queue.list_tasks,
        limit,
        status,
        source,
        entity_id,
        idempotency_key,
    )
    return {
        "count": len(tasks),
        "items": [_build_task_view(task) for task in tasks],
    }


@router.get("/tasks/{task_id}")
async def get_dispatch_task(task_id: str) -> Dict[str, Any]:
    task = await asyncio.to_thread(print_dispatch_queue.get_task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Tarea {task_id} no encontrada.")
    return {"task": _build_task_view(task)}


@router.post("/tasks/{task_id}/retry")
async def retry_dispatch_task(task_id: str, request: RetryDispatchTaskRequest) -> Dict[str, Any]:
    try:
        task = await asyncio.to_thread(
            print_dispatch_queue.retry_task,
            task_id,
            reset_attempts=request.reset_attempts,
            clear_result=request.clear_result,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if not task:
        raise HTTPException(status_code=404, detail=f"Tarea {task_id} no encontrada.")
    return {"ok": True, "task": _build_task_view(task)}


@router.get("/stats")
async def get_dispatch_stats(source: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    stats = await asyncio.to_thread(print_dispatch_queue.get_stats, source)
    return stats

