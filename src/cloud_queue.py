"""
Cloud print queue stored in local SQLite database.
This is isolated from the legacy direct-print flow.
"""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any, Dict, List, Optional

from database import db


class CloudPrintQueueService:
    def __init__(self) -> None:
        self._init_tables()

    def _init_tables(self) -> None:
        with db.connection.get_cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cloud_print_tasks (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    shipment_id TEXT NOT NULL,
                    payload_type TEXT NOT NULL DEFAULT 'pdf_base64',
                    payload_b64 TEXT NOT NULL,
                    printer_hint TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_by TEXT,
                    claimed_by TEXT,
                    result_message TEXT,
                    error_message TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    claimed_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cloud_tasks_status_created
                ON cloud_print_tasks(status, created_at)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cloud_tasks_printer
                ON cloud_print_tasks(printer_hint)
                """
            )

    @staticmethod
    def _row_to_dict(cursor, row) -> Dict[str, Any]:
        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))
        if data.get("metadata"):
            try:
                data["metadata"] = json.loads(data["metadata"])
            except Exception:
                data["metadata"] = {}
        else:
            data["metadata"] = {}
        return data

    def enqueue_pdf_task(
        self,
        source: str,
        shipment_id: str,
        pdf_bytes: bytes,
        created_by: str,
        printer_hint: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task_id = uuid.uuid4().hex
        payload_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        metadata_json = json.dumps(metadata or {}, ensure_ascii=True)
        with db.connection.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cloud_print_tasks
                (id, source, shipment_id, payload_type, payload_b64, printer_hint, status, created_by, metadata)
                VALUES (?, ?, ?, 'pdf_base64', ?, ?, 'pending', ?, ?)
                """,
                (task_id, source, shipment_id, payload_b64, (printer_hint or "").strip(), created_by, metadata_json),
            )
        return self.get_task(task_id, include_payload=False) or {
            "id": task_id,
            "status": "pending",
        }

    def get_task(self, task_id: str, include_payload: bool = False) -> Optional[Dict[str, Any]]:
        with db.connection.get_cursor() as cursor:
            cursor.execute("SELECT * FROM cloud_print_tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = self._row_to_dict(cursor, row)
            if not include_payload:
                data.pop("payload_b64", None)
            return data

    def list_tasks(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with db.connection.get_cursor() as cursor:
            if status:
                cursor.execute(
                    """
                    SELECT * FROM cloud_print_tasks
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (status, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM cloud_print_tasks
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            rows = cursor.fetchall()
            tasks = [self._row_to_dict(cursor, row) for row in rows]
            for task in tasks:
                task.pop("payload_b64", None)
            return tasks

    def claim_next_task(
        self,
        agent_id: str,
        accepted_printers: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        accepted = [p.strip() for p in (accepted_printers or []) if p and p.strip()]

        for _ in range(4):
            with db.connection.get_cursor() as cursor:
                if accepted:
                    placeholders = ",".join("?" for _ in accepted)
                    query = (
                        "SELECT id FROM cloud_print_tasks "
                        "WHERE status = 'pending' "
                        f"AND (printer_hint IS NULL OR printer_hint = '' OR printer_hint IN ({placeholders})) "
                        "ORDER BY created_at ASC LIMIT 1"
                    )
                    cursor.execute(query, tuple(accepted))
                else:
                    cursor.execute(
                        """
                        SELECT id FROM cloud_print_tasks
                        WHERE status = 'pending'
                        ORDER BY created_at ASC
                        LIMIT 1
                        """
                    )
                row = cursor.fetchone()
                if not row:
                    return None
                task_id = row[0]
                cursor.execute(
                    """
                    UPDATE cloud_print_tasks
                    SET status = 'claimed',
                        claimed_by = ?,
                        claimed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'pending'
                    """,
                    (agent_id, task_id),
                )
                if cursor.rowcount == 1:
                    task = self.get_task(task_id, include_payload=True)
                    if task:
                        return task
        return None

    def complete_task(
        self,
        task_id: str,
        agent_id: str,
        success: bool,
        result_message: str = "",
        error_message: str = "",
    ) -> bool:
        final_status = "completed" if success else "failed"
        with db.connection.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE cloud_print_tasks
                SET status = ?,
                    result_message = ?,
                    error_message = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND status IN ('claimed', 'pending')
                  AND (claimed_by = ? OR claimed_by IS NULL OR claimed_by = '')
                """,
                (final_status, result_message.strip(), error_message.strip(), task_id, agent_id),
            )
            return cursor.rowcount == 1


cloud_print_queue = CloudPrintQueueService()

