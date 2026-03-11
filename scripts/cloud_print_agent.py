"""
Cloud print agent for the PC connected to the USB/network printer.

Usage example:
python scripts/cloud_print_agent.py --server http://192.168.54.51:8002 --username agent1 --password secret123 --agent-id PC-IMPRESORA --printer "Godex GE300"
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from administrado_integration import administrado_integration  # noqa: E402


class CloudPrintAgent:
    def __init__(
        self,
        server: str,
        username: str,
        password: str,
        agent_id: str,
        printer: str,
        poll_seconds: int,
    ) -> None:
        self.server = server.rstrip("/")
        self.username = username
        self.password = password
        self.agent_id = agent_id
        self.printer = printer.strip()
        self.poll_seconds = max(2, int(poll_seconds))
        self.token: Optional[str] = None

    def _headers(self) -> Dict[str, str]:
        if not self.token:
            return {"Content-Type": "application/json"}
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    def login(self) -> None:
        response = requests.post(
            f"{self.server}/api/auth/login",
            json={"username": self.username, "password": self.password},
            timeout=20,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Login fallido ({response.status_code}): {response.text}")
        data = response.json()
        self.token = data.get("access_token")
        if not self.token:
            raise RuntimeError("Login sin token")
        print(f"[agent] login ok: {data.get('username')} ({data.get('role')})")

    def _claim_task(self) -> Optional[Dict[str, Any]]:
        payload = {
            "agent_id": self.agent_id,
            "printers": [self.printer] if self.printer else [],
        }
        response = requests.post(
            f"{self.server}/api/cloud/tasks/claim",
            headers=self._headers(),
            data=json.dumps(payload),
            timeout=30,
        )
        if response.status_code == 401:
            self.login()
            return None
        if response.status_code != 200:
            raise RuntimeError(f"Claim fallido ({response.status_code}): {response.text}")
        data = response.json()
        return data.get("task")

    def _complete_task(self, task_id: str, success: bool, result_message: str, error_message: str = "") -> None:
        payload = {
            "success": bool(success),
            "result_message": result_message,
            "error_message": error_message,
        }
        response = requests.post(
            f"{self.server}/api/cloud/tasks/{task_id}/complete",
            headers=self._headers(),
            data=json.dumps(payload),
            timeout=30,
        )
        if response.status_code == 401:
            self.login()
            response = requests.post(
                f"{self.server}/api/cloud/tasks/{task_id}/complete",
                headers=self._headers(),
                data=json.dumps(payload),
                timeout=30,
            )
        if response.status_code != 200:
            raise RuntimeError(f"Complete fallido ({response.status_code}): {response.text}")

    def _process_task(self, task: Dict[str, Any]) -> None:
        task_id = task.get("id", "")
        source = task.get("source", "unknown")
        shipment_id = str(task.get("shipment_id", "")).strip()
        payload_b64 = task.get("payload_b64", "")
        printer_hint = (task.get("printer_hint") or "").strip()
        selected_printer = self.printer or printer_hint

        if not task_id or not shipment_id or not payload_b64:
            raise RuntimeError("Task incompleto")

        pdf_bytes = base64.b64decode(payload_b64)
        result = administrado_integration.process_downloaded_pdf(
            pdf_bytes=pdf_bytes,
            envio_id=shipment_id,
            printer=selected_printer,
        )
        ok = bool(result.get("success"))
        if not ok:
            raise RuntimeError(f"Impresion reportada como fallo: {result}")
        print(f"[agent] task {task_id} ({source} {shipment_id}) impresa en {result.get('printer')}")

    def run(self) -> None:
        self.login()
        print(f"[agent] iniciado. server={self.server} agent_id={self.agent_id} poll={self.poll_seconds}s")
        while True:
            try:
                task = self._claim_task()
                if not task:
                    time.sleep(self.poll_seconds)
                    continue

                task_id = task.get("id", "")
                try:
                    self._process_task(task)
                    self._complete_task(task_id, True, "Impresion completada")
                except Exception as task_error:
                    self._complete_task(task_id, False, "", str(task_error))
                    print(f"[agent] task {task_id} fallo: {task_error}")
            except KeyboardInterrupt:
                print("[agent] detenido por usuario")
                break
            except Exception as loop_error:
                print(f"[agent] error de loop: {loop_error}")
                time.sleep(self.poll_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EtiquetadorZPL Cloud Print Agent")
    parser.add_argument("--server", required=True, help="URL base de la API cloud, ejemplo: http://192.168.54.51:8002")
    parser.add_argument("--username", required=True, help="Usuario de rol agent o admin")
    parser.add_argument("--password", required=True, help="Password del usuario")
    parser.add_argument("--agent-id", default="agent-local", help="Identificador unico del agente")
    parser.add_argument("--printer", default="", help="Impresora fija (opcional)")
    parser.add_argument("--poll-seconds", type=int, default=5, help="Intervalo de polling en segundos")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    agent = CloudPrintAgent(
        server=args.server,
        username=args.username,
        password=args.password,
        agent_id=args.agent_id,
        printer=args.printer,
        poll_seconds=args.poll_seconds,
    )
    agent.run()


if __name__ == "__main__":
    main()

