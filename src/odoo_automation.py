"""
Worker de automatizacion Odoo + Administrado para impresion en deposito.
No reemplaza el flujo existente: funciona en paralelo y de forma opcional.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from administrado_integration import administrado_integration
from odoo_integration import odoo_integration
from print_fallbacks import download_and_print_label_with_fallback, print_order_pdf_with_fallback

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OdooAutomationWorker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.state_path = self._resolve_state_path()
        self.state = self._load_state()

    def _resolve_state_path(self) -> Path:
        try:
            from config_manager import config_manager

            return Path(config_manager.get_config_directory()) / "odoo_automation_state.json"
        except Exception:
            import os

            if os.name == "nt":
                base_dir = Path(os.environ.get("APPDATA", "."))
            else:
                base_dir = Path.home() / ".config"
            config_dir = base_dir / "EtiquetadorZPL"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / "odoo_automation_state.json"

    def _default_state(self) -> Dict[str, Any]:
        return {
            "processed_envios": {},
            "last_cycle_started_at": "",
            "last_cycle_finished_at": "",
            "last_cycle_result": {},
            "last_error": "",
            "recent_events": [],
        }

    def _load_state(self) -> Dict[str, Any]:
        state = self._default_state()
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                state.update(saved)
            except Exception as exc:
                logger.warning("No se pudo cargar estado de automatizacion Odoo: %s", exc)
        if not isinstance(state.get("processed_envios"), dict):
            state["processed_envios"] = {}
        if not isinstance(state.get("recent_events"), list):
            state["recent_events"] = []
        return state

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=2, ensure_ascii=True)

    def _push_event(self, message: str) -> None:
        event = {"at": _utc_now_iso(), "message": message}
        events = self.state.get("recent_events", [])
        events.append(event)
        self.state["recent_events"] = events[-120:]

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="odoo-automation-worker", daemon=True)
        self._thread.start()
        logger.info("Worker Odoo automation iniciado")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Worker Odoo automation detenido")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as exc:
                logger.exception("Error inesperado en ciclo de automatizacion Odoo: %s", exc)
                message = odoo_integration.humanize_exception(exc)
                with self._lock:
                    self.state["last_error"] = message
                    self._push_event(f"Error general: {message}")
                    self._save_state()

            interval = int(odoo_integration.config.get("automation_interval_seconds", 60) or 60)
            if interval < 15:
                interval = 15
            self._stop_event.wait(interval)

    def _get_processed_map(self) -> Dict[str, str]:
        processed = self.state.get("processed_envios", {})
        if not isinstance(processed, dict):
            processed = {}
            self.state["processed_envios"] = processed
        return processed

    def _mark_processed(self, envio_id: str) -> None:
        processed = self._get_processed_map()
        processed[str(envio_id)] = _utc_now_iso()
        # Mantener memoria acotada.
        if len(processed) > 5000:
            items = sorted(processed.items(), key=lambda item: item[1], reverse=True)[:5000]
            self.state["processed_envios"] = dict(items)

    def reset_processed(self) -> Dict[str, Any]:
        with self._lock:
            self.state["processed_envios"] = {}
            self._push_event("Memoria de envios procesados reiniciada manualmente")
            self._save_state()
            return {
                "success": True,
                "processed_count": 0,
            }

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            processed = self._get_processed_map()
            recent_processed = sorted(processed.items(), key=lambda item: item[1], reverse=True)[:20]
            return {
                "running": bool(self._thread and self._thread.is_alive()),
                "state_path": str(self.state_path),
                "processed_count": len(processed),
                "recent_processed_envios": [
                    {"envio_id": envio_id, "at": timestamp}
                    for envio_id, timestamp in recent_processed
                ],
                "last_cycle_started_at": self.state.get("last_cycle_started_at"),
                "last_cycle_finished_at": self.state.get("last_cycle_finished_at"),
                "last_cycle_result": self.state.get("last_cycle_result", {}),
                "last_error": self.state.get("last_error", ""),
                "recent_events": self.state.get("recent_events", [])[-20:],
                "odoo_automation_enabled": bool(odoo_integration.config.get("automation_enabled")),
                "odoo_integration_enabled": bool(odoo_integration.config.get("enabled")),
                "odoo_configured": odoo_integration.is_configured(),
            }

    def run_once(self) -> Dict[str, Any]:
        return self.run_cycle(force=True)

    def _get_order_to_label_delay_seconds(self) -> int:
        raw_delay = odoo_integration.config.get("automation_order_to_label_delay_seconds", 1)
        try:
            delay_seconds = int(raw_delay)
        except (TypeError, ValueError):
            delay_seconds = 1
        return max(0, min(delay_seconds, 30))

    def _prioritize_sales(
        self,
        sales: List[Dict[str, Any]],
        include_reprint: bool,
        sync_limit: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        non_reprint = [sale for sale in sales if sale.get("print_mode") != "reimprimir"]
        reprint = [sale for sale in sales if sale.get("print_mode") == "reimprimir"]

        if include_reprint:
            prioritized = non_reprint + reprint
            skipped_reprint = 0
        else:
            prioritized = non_reprint
            skipped_reprint = len(reprint)

        return prioritized[:sync_limit], skipped_reprint

    def _print_order_with_fallback(self, pdf_bytes: bytes, envio_id: str) -> Tuple[bool, Dict[str, Any]]:
        result = print_order_pdf_with_fallback(
            envio_id=envio_id,
            pdf_bytes=pdf_bytes,
        )
        return bool(result.get("success")), result

    def _print_label_with_fallback(self, envio_id: str) -> Tuple[bool, Dict[str, Any]]:
        result = download_and_print_label_with_fallback(envio_id=envio_id)
        return bool(result.get("success")), result

    def run_cycle(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            self.state["last_cycle_started_at"] = _utc_now_iso()
            self.state["last_error"] = ""
            self._save_state()

        odoo_enabled = bool(odoo_integration.config.get("enabled"))
        automation_enabled = bool(odoo_integration.config.get("automation_enabled"))
        if not force and (not odoo_enabled or not automation_enabled):
            result = {
                "ok": True,
                "skipped": True,
                "reason": "automation_disabled",
                "odoo_enabled": odoo_enabled,
                "automation_enabled": automation_enabled,
            }
            with self._lock:
                self.state["last_cycle_finished_at"] = _utc_now_iso()
                self.state["last_cycle_result"] = result
                self._save_state()
            return result

        if not odoo_integration.is_configured():
            raise ValueError("Configuracion Odoo incompleta para automatizacion")
        if not administrado_integration.get_public_config().get("configured"):
            raise ValueError("Configuracion de Administrado incompleta para automatizacion")

        include_reprint = bool(odoo_integration.config.get("automation_include_reprint"))
        sync_limit = int(odoo_integration.config.get("automation_sync_limit", 20) or 20)
        if sync_limit < 1:
            sync_limit = 1
        if sync_limit > 50:
            sync_limit = 50
        order_to_label_delay_seconds = self._get_order_to_label_delay_seconds()

        # Si no se incluyen reimpresiones, traemos una ventana mas grande para
        # no quedar bloqueados en "reimprimir" al inicio del dia.
        fetch_limit = sync_limit if include_reprint else min(200, max(sync_limit * 5, sync_limit))
        sales = administrado_integration.list_label_links(fetch_limit)
        sales_to_process, skipped_reprint = self._prioritize_sales(sales, include_reprint, sync_limit)
        processed_map = self._get_processed_map()

        checked = 0
        printed = 0
        skipped_already = 0
        missing_order = 0
        errors = 0
        printed_envios: List[str] = []

        for sale in sales_to_process:
            envio_id = str(sale.get("envio_id", "")).strip()
            if not envio_id:
                continue

            checked += 1
            if envio_id in processed_map:
                skipped_already += 1
                continue

            if sale.get("print_mode") == "reimprimir" and not include_reprint:
                skipped_reprint += 1
                continue

            try:
                order = odoo_integration.find_sale_order_by_envio(envio_id)
                if not order:
                    missing_order += 1
                    self._push_event(f"Envio {envio_id}: no se encontro orden en Odoo")
                    continue

                pdf_bytes = odoo_integration.download_sale_order_report_pdf(
                    order_id=int(order["id"]),
                    report_name=str(odoo_integration.config.get("report_name", "")),
                )

                order_ok, order_result = self._print_order_with_fallback(pdf_bytes, envio_id)
                if not order_ok:
                    errors += 1
                    self._push_event(
                        f"Envio {envio_id}: fallo impresion orden Odoo ({order_result.get('printer', '-')})"
                    )
                    continue

                if order_to_label_delay_seconds > 0:
                    time.sleep(order_to_label_delay_seconds)

                label_ok, label_result = self._print_label_with_fallback(envio_id)
                if not label_ok:
                    errors += 1
                    self._push_event(
                        f"Envio {envio_id}: orden impresa, fallo etiqueta ({label_result.get('printer', '-')})"
                    )
                    continue

                self._mark_processed(envio_id)
                printed += 1
                printed_envios.append(envio_id)
                self._push_event(
                    f"Envio {envio_id}: OK orden={order_result.get('printer')} etiqueta={label_result.get('printer')}"
                )
            except Exception as exc:
                errors += 1
                logger.exception("Error procesando envio %s", envio_id)
                message = odoo_integration.humanize_exception(exc)
                self._push_event(f"Envio {envio_id}: error {message}")

        result = {
            "ok": errors == 0,
            "skipped": False,
            "checked": checked,
            "printed": printed,
            "printed_envios": printed_envios,
            "skipped_already": skipped_already,
            "skipped_reprint": skipped_reprint,
            "missing_order": missing_order,
            "errors": errors,
            "sales_count": len(sales),
            "selected_count": len(sales_to_process),
            "fetch_limit": fetch_limit,
            "order_to_label_delay_seconds": order_to_label_delay_seconds,
        }

        with self._lock:
            self.state["last_cycle_finished_at"] = _utc_now_iso()
            self.state["last_cycle_result"] = result
            self._save_state()

        return result


odoo_automation_worker = OdooAutomationWorker()
