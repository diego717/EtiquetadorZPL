"""
Cola persistente para despachos de impresion con idempotencia y reintentos.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from database import db


class PrintDispatchQueueService:
    def __init__(self) -> None:
        self._init_lock = threading.Lock()
        self._init_tables()

    def _init_tables(self) -> None:
        with self._init_lock:
            with db.connection.get_cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS print_dispatch_tasks (
                        id TEXT PRIMARY KEY,
                        source TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        request_payload TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL DEFAULT 3,
                        last_error TEXT,
                        result_payload TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_attempt_at TIMESTAMP,
                        next_retry_at TIMESTAMP,
                        completed_at TIMESTAMP
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_dispatch_tasks_status_retry
                    ON print_dispatch_tasks(status, next_retry_at, created_at)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_dispatch_tasks_entity
                    ON print_dispatch_tasks(source, entity_id, action)
                    """
                )

    @staticmethod
    def _json_dumps(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=True, default=str)
        except Exception:
            return json.dumps({"_raw": str(value)}, ensure_ascii=True)

    @staticmethod
    def _json_loads(value: Any) -> Any:
        if not value:
            return None
        try:
            return json.loads(value)
        except Exception:
            return value

    @staticmethod
    def _row_to_dict(cursor, row) -> Dict[str, Any]:
        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))
        data["request_payload"] = PrintDispatchQueueService._json_loads(data.get("request_payload"))
        data["result_payload"] = PrintDispatchQueueService._json_loads(data.get("result_payload"))
        return data

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with db.connection.get_cursor() as cursor:
            cursor.execute("SELECT * FROM print_dispatch_tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(cursor, row)

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        with db.connection.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM print_dispatch_tasks WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(cursor, row)

    def list_tasks(
        self,
        limit: int = 50,
        status: Optional[str] = None,
        source: Optional[str] = None,
        entity_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 50), 500))
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(str(status).strip())
        if source:
            clauses.append("source = ?")
            params.append(str(source).strip())
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(str(entity_id).strip())
        if idempotency_key:
            clauses.append("idempotency_key = ?")
            params.append(str(idempotency_key).strip())

        where_sql = ""
        if clauses:
            where_sql = "WHERE " + " AND ".join(clauses)

        with db.connection.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT * FROM print_dispatch_tasks
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple(params + [safe_limit]),
            )
            rows = cursor.fetchall()
            return [self._row_to_dict(cursor, row) for row in rows]

    def get_stats(self, source: Optional[str] = None) -> Dict[str, Any]:
        where_sql = ""
        params: list[Any] = []
        if source:
            where_sql = "WHERE source = ?"
            params.append(str(source).strip())

        with db.connection.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT status, COUNT(*) as count
                FROM print_dispatch_tasks
                {where_sql}
                GROUP BY status
                """,
                tuple(params),
            )
            rows = cursor.fetchall()

        counts = {
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
        }
        total = 0
        for status_value, count_value in rows:
            key = str(status_value or "").strip().lower()
            count_num = int(count_value or 0)
            total += count_num
            if key in counts:
                counts[key] = count_num
            else:
                counts[key] = count_num
        return {
            "source": source or None,
            "total": total,
            "counts": counts,
        }

    def retry_task(
        self,
        task_id: str,
        *,
        reset_attempts: bool = True,
        clear_result: bool = False,
    ) -> Optional[Dict[str, Any]]:
        current = self.get_task(task_id)
        if not current:
            return None
        if current.get("status") == "processing":
            raise RuntimeError("No se puede reintentar una tarea en procesamiento.")

        updates = [
            "status = 'pending'",
            "last_error = NULL",
            "next_retry_at = NULL",
            "completed_at = NULL",
            "updated_at = CURRENT_TIMESTAMP",
        ]
        params: list[Any] = []
        if reset_attempts:
            updates.append("attempt_count = 0")
        if clear_result:
            updates.append("result_payload = NULL")

        with db.connection.get_cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE print_dispatch_tasks
                SET {', '.join(updates)}
                WHERE id = ?
                """,
                tuple(params + [task_id]),
            )
        return self.get_task(task_id)

    def create_task(
        self,
        *,
        source: str,
        entity_id: str,
        action: str,
        idempotency_key: str,
        request_payload: Optional[Dict[str, Any]],
        max_attempts: int,
    ) -> Dict[str, Any]:
        task_id = uuid.uuid4().hex
        payload_json = self._json_dumps(request_payload or {})
        try:
            with db.connection.get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO print_dispatch_tasks
                    (id, source, entity_id, action, idempotency_key, request_payload, status, attempt_count, max_attempts)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?)
                    """,
                    (
                        task_id,
                        source.strip(),
                        entity_id.strip(),
                        action.strip(),
                        idempotency_key.strip(),
                        payload_json,
                        max(1, int(max_attempts)),
                    ),
                )
        except Exception:
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing
            raise
        task = self.get_task(task_id)
        if not task:
            raise RuntimeError("No se pudo crear tarea de despacho")
        return task

    def _can_attempt_now(self, task: Dict[str, Any]) -> bool:
        if not task:
            return False
        if task.get("status") == "completed":
            return False
        attempts = int(task.get("attempt_count") or 0)
        max_attempts = int(task.get("max_attempts") or 0)
        if attempts >= max_attempts:
            return False
        next_retry_at = task.get("next_retry_at")
        if not next_retry_at:
            return True
        try:
            retry_dt = datetime.fromisoformat(str(next_retry_at).replace("Z", "+00:00"))
            return datetime.now(timezone.utc) >= retry_dt.astimezone(timezone.utc)
        except Exception:
            return True

    def _claim_for_processing(self, task_id: str) -> bool:
        with db.connection.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE print_dispatch_tasks
                SET status = 'processing',
                    updated_at = CURRENT_TIMESTAMP,
                    last_attempt_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND status IN ('pending', 'failed')
                  AND attempt_count < max_attempts
                """,
                (task_id,),
            )
            return cursor.rowcount == 1

    def _mark_success(self, task_id: str, result_payload: Any) -> Dict[str, Any]:
        with db.connection.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE print_dispatch_tasks
                SET status = 'completed',
                    result_payload = ?,
                    last_error = NULL,
                    next_retry_at = NULL,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (self._json_dumps(result_payload), task_id),
            )
        task = self.get_task(task_id)
        if not task:
            raise RuntimeError("No se pudo actualizar tarea completada")
        return task

    def _mark_failure(
        self,
        task_id: str,
        *,
        error_message: str,
        retry_delay_seconds: int,
    ) -> Dict[str, Any]:
        current = self.get_task(task_id)
        if not current:
            raise RuntimeError("No se encontro tarea para registrar fallo")

        attempt_count = int(current.get("attempt_count") or 0) + 1
        max_attempts = int(current.get("max_attempts") or 1)
        exhausted = attempt_count >= max_attempts

        next_retry_at = None
        status = "failed"
        completed_at_sql = "CURRENT_TIMESTAMP"
        if not exhausted:
            status = "pending"
            completed_at_sql = "NULL"
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, int(retry_delay_seconds)))
            next_retry_at = retry_at.isoformat()

        with db.connection.get_cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE print_dispatch_tasks
                SET status = ?,
                    attempt_count = ?,
                    last_error = ?,
                    next_retry_at = ?,
                    completed_at = {completed_at_sql},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    status,
                    attempt_count,
                    str(error_message or "").strip(),
                    next_retry_at,
                    task_id,
                ),
            )

        task = self.get_task(task_id)
        if not task:
            raise RuntimeError("No se pudo actualizar tarea fallida")
        return task

    def execute_with_idempotency(
        self,
        *,
        source: str,
        entity_id: str,
        action: str,
        idempotency_key: str,
        request_payload: Optional[Dict[str, Any]],
        executor: Callable[[], Dict[str, Any]],
        max_attempts: int = 3,
        initial_retry_delay_seconds: int = 1,
        max_retry_delay_seconds: int = 8,
    ) -> Dict[str, Any]:
        task = self.get_by_idempotency_key(idempotency_key)
        created = False
        if not task:
            task = self.create_task(
                source=source,
                entity_id=entity_id,
                action=action,
                idempotency_key=idempotency_key,
                request_payload=request_payload,
                max_attempts=max_attempts,
            )
            created = True

        if task.get("status") == "completed":
            return {
                "status": "completed",
                "reused": True,
                "created": created,
                "task": task,
                "result": task.get("result_payload"),
                "error": None,
            }

        if task.get("status") == "processing":
            return {
                "status": "processing",
                "reused": True,
                "created": created,
                "task": task,
                "result": None,
                "error": task.get("last_error"),
            }

        if int(task.get("attempt_count") or 0) >= int(task.get("max_attempts") or 0):
            return {
                "status": "failed",
                "reused": True,
                "created": created,
                "task": task,
                "result": task.get("result_payload"),
                "error": task.get("last_error") or "Se alcanzaron los reintentos maximos.",
            }

        retry_delay = max(0, int(initial_retry_delay_seconds))
        while True:
            task = self.get_task(task["id"])
            if not task:
                raise RuntimeError("Tarea de despacho no encontrada")

            if task.get("status") == "completed":
                return {
                    "status": "completed",
                    "reused": not created,
                    "created": created,
                    "task": task,
                    "result": task.get("result_payload"),
                    "error": None,
                }

            if task.get("status") == "processing":
                return {
                    "status": "processing",
                    "reused": not created,
                    "created": created,
                    "task": task,
                    "result": None,
                    "error": task.get("last_error"),
                }

            if not self._can_attempt_now(task):
                attempts = int(task.get("attempt_count") or 0)
                max_attempts = int(task.get("max_attempts") or 0)
                if attempts >= max_attempts:
                    return {
                        "status": "failed",
                        "reused": not created,
                        "created": created,
                        "task": task,
                        "result": task.get("result_payload"),
                        "error": task.get("last_error") or "No hay mas reintentos disponibles.",
                    }
                if task.get("status") == "processing":
                    return {
                        "status": "processing",
                        "reused": True,
                        "created": created,
                        "task": task,
                        "result": None,
                        "error": task.get("last_error"),
                    }
                time.sleep(0.1)
                continue

            claimed = self._claim_for_processing(task["id"])
            if not claimed:
                # Otra solicitud se adueno de la tarea.
                latest = self.get_task(task["id"]) or task
                if latest.get("status") == "completed":
                    return {
                        "status": "completed",
                        "reused": True,
                        "created": created,
                        "task": latest,
                        "result": latest.get("result_payload"),
                        "error": None,
                    }
                if latest.get("status") == "processing":
                    return {
                        "status": "processing",
                        "reused": True,
                        "created": created,
                        "task": latest,
                        "result": None,
                        "error": latest.get("last_error"),
                    }
                time.sleep(0.05)
                continue

            try:
                result = executor()
                latest = self._mark_success(task["id"], result)
                return {
                    "status": "completed",
                    "reused": False,
                    "created": created,
                    "task": latest,
                    "result": result,
                    "error": None,
                }
            except Exception as exc:
                latest = self._mark_failure(
                    task["id"],
                    error_message=str(exc),
                    retry_delay_seconds=retry_delay,
                )
                if latest.get("status") == "failed":
                    return {
                        "status": "failed",
                        "reused": False,
                        "created": created,
                        "task": latest,
                        "result": latest.get("result_payload"),
                        "error": latest.get("last_error") or str(exc),
                    }
                time.sleep(retry_delay)
                retry_delay = min(max_retry_delay_seconds, max(1, retry_delay * 2))


print_dispatch_queue = PrintDispatchQueueService()
