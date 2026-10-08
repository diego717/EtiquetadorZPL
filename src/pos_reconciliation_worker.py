"""
Conciliacion POS asistida en segundo plano.

Cada cierto tiempo sincroniza TotalNet contra Odoo, guarda la propuesta para que
el operador la revise y avisa cuando hay pagos nuevos listos. Solo registra
pagos por su cuenta si `auto_register_deterministic` esta activo y la
coincidencia pasa `find_deterministic_matches`; todo lo demas queda para
confirmacion humana.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pos_reconciliation as recon
import pos_reconciliation_service as service
from odoo_integration import odoo_integration
from totalnet_integration import totalnet_integration

logger = logging.getLogger(__name__)

MAX_AUTO_REGISTER_PER_CYCLE = 20
MAX_NOTIFIED_IDS = 5000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(number, max_value))


class PosReconciliationWorker:
    def __init__(self, totalnet: Any = None, odoo: Any = None, notifier: Any = None) -> None:
        self.totalnet = totalnet or totalnet_integration
        self.odoo = odoo or odoo_integration
        self._notifier = notifier
        # RLock: _push_event se llama tanto dentro como fuera de secciones con lock.
        self._lock = threading.RLock()
        self._cycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.state_path = recon._resolve_state_path("pos_reconciliation_auto_state.json")
        self.state = self._load_state()

    # ---- estado ----
    @staticmethod
    def _default_state() -> Dict[str, Any]:
        return {
            "last_cycle_started_at": "",
            "last_cycle_finished_at": "",
            "last_error": "",
            "last_summary": {},
            "last_proposal": None,
            "notified_cupon_ids": [],
            "recent_events": [],
        }

    def _load_state(self) -> Dict[str, Any]:
        state = self._default_state()
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as handle:
                    state.update(json.load(handle))
            except Exception as exc:
                logger.warning("No se pudo leer estado de conciliacion POS automatica: %s", exc)
        return state

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=1, ensure_ascii=True)

    def _push_event(self, message: str) -> None:
        with self._lock:
            events = self.state.get("recent_events", [])
            events.append({"at": _utc_now_iso(), "message": message})
            self.state["recent_events"] = events[-100:]

    @staticmethod
    def _schedule(config: Dict[str, Any]) -> Dict[str, int]:
        return {
            "interval_minutes": _clamp_int(
                config.get("auto_sync_interval_minutes"), recon.DEFAULT_AUTO_SYNC_INTERVAL_MINUTES, 15, 1440
            ),
            "lookback_days": _clamp_int(
                config.get("auto_sync_lookback_days"), recon.DEFAULT_AUTO_SYNC_LOOKBACK_DAYS, 1, 31
            ),
        }

    def get_status(self) -> Dict[str, Any]:
        config = recon.load_recon_config()
        with self._lock:
            return {
                "running": bool(self._thread and self._thread.is_alive()),
                "cycle_in_progress": self._cycle_lock.locked(),
                "enabled": bool(config.get("auto_sync_enabled")),
                "auto_register_deterministic": bool(config.get("auto_register_deterministic")),
                "auto_register_operator": str(config.get("auto_register_operator") or ""),
                **self._schedule(config),
                "last_cycle_started_at": self.state.get("last_cycle_started_at", ""),
                "last_cycle_finished_at": self.state.get("last_cycle_finished_at", ""),
                "last_error": self.state.get("last_error", ""),
                "last_summary": self.state.get("last_summary", {}),
                "has_proposal": bool(self.state.get("last_proposal")),
                "recent_events": self.state.get("recent_events", [])[-20:],
            }

    def get_last_proposal(self) -> Optional[Dict[str, Any]]:
        """Ultima propuesta, sin los cupones que ya se registraron despues de generarla."""
        with self._lock:
            proposal = self.state.get("last_proposal")
        if not proposal:
            return None
        processed = recon.load_processed_cupon_ids()
        filtered = dict(proposal)
        for bucket in ("matches_unicos", "ambiguos", "sin_match"):
            filtered[bucket] = [
                row
                for row in proposal.get(bucket, []) or []
                if str((row.get("cupon") or {}).get("cupon_id")) not in processed
            ]
        return filtered

    # ---- ciclo ----
    def _auto_register(
        self, proposal: Dict[str, Any], config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        operator = str(config.get("auto_register_operator") or "").strip().lower()
        if not operator:
            self._push_event("Registro automatico activo pero sin operador Odoo asignado: no se registro nada")
            return []
        auth_override = self.odoo.resolve_operator_auth_exact(operator)
        if not auth_override:
            self._push_event(f"El operador '{operator}' no tiene credenciales Odoo: no se registro nada")
            return []
        actor = str(auth_override.get("username") or "").strip()

        candidates = recon.find_deterministic_matches(proposal)[:MAX_AUTO_REGISTER_PER_CYCLE]
        results: List[Dict[str, Any]] = []
        for match in candidates:
            cupon = match["cupon"]
            invoice = match["invoice"]
            entry: Dict[str, Any] = {
                "cupon_id": cupon.get("cupon_id"),
                "cupon": dict(cupon),
                "invoice_id": invoice.get("invoice_id"),
                "invoice_name": invoice.get("name"),
                "operator_app_username": operator,
                "actor_odoo_username": actor,
                "mode": "automatico_deterministico",
            }
            try:
                entry.update(
                    service.register_confirmed_payment(
                        self.odoo,
                        cupon,
                        int(invoice["invoice_id"]),
                        str(invoice.get("name") or ""),
                        int(match["suggested_journal_id"]),
                        str(match.get("suggested_memo") or ""),
                        auth_override,
                    )
                )
                self._push_event(
                    f"Pago registrado automaticamente: cupon {cupon.get('cupon_id')} -> {invoice.get('name')}"
                )
            except Exception as exc:
                entry["ok"] = False
                entry["error"] = str(exc) or "Error registrando el pago"
                self._push_event(
                    f"No se pudo registrar automaticamente el cupon {cupon.get('cupon_id')}: {entry['error']}"
                )
            results.append(entry)

        registered_ids = [entry["cupon_id"] for entry in results if entry.get("ok")]
        if registered_ids:
            recon.mark_cupones_processed(registered_ids, results)
        return results

    def _notify(self, title: str, message: str) -> None:
        try:
            notifier = self._notifier
            if notifier is None:
                from notifications import notification_manager

                notifier = notification_manager
            # El mensaje viaja dentro de un script PowerShell: evitar comillas.
            notifier._send_notification(title, message.replace('"', "").replace("'", ""))
        except Exception as exc:
            logger.warning("No se pudo enviar notificacion de conciliacion POS: %s", exc)

    def run_cycle(self, force: bool = False) -> Dict[str, Any]:
        config = recon.load_recon_config()
        if not force and not config.get("auto_sync_enabled"):
            return {"ok": True, "skipped": True, "reason": "auto_sync_disabled"}
        if not self._cycle_lock.acquire(blocking=False):
            return {"ok": False, "skipped": True, "reason": "cycle_in_progress"}
        try:
            with self._lock:
                self.state["last_cycle_started_at"] = _utc_now_iso()
                self._save_state()
            try:
                summary = self._run_cycle_locked(config)
                error = ""
            except Exception as exc:
                logger.exception("Error en conciliacion POS automatica")
                summary = None
                error = str(exc) or "Error inesperado en conciliacion POS automatica"
            with self._lock:
                self.state["last_cycle_finished_at"] = _utc_now_iso()
                self.state["last_error"] = error
                if error:
                    self._push_event(f"Error: {error}")
                else:
                    self.state["last_summary"] = summary
                self._save_state()
            if error:
                return {"ok": False, "error": error}
            return {"ok": True, "skipped": False, "summary": summary}
        finally:
            self._cycle_lock.release()

    def _run_cycle_locked(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if not self.totalnet.is_configured():
            raise ValueError("TotalNet no esta configurado")
        if not self.odoo.is_configured():
            raise ValueError("Odoo no esta configurado")

        schedule = self._schedule(config)
        # TotalNet solo expone hasta el dia anterior.
        date_to = date.today() - timedelta(days=1)
        date_from = date_to - timedelta(days=schedule["lookback_days"] - 1)
        proposal = service.build_sync_proposal(
            self.totalnet, self.odoo, date_from.isoformat(), date_to.isoformat()
        )

        auto_results: List[Dict[str, Any]] = []
        if config.get("auto_register_deterministic"):
            auto_results = self._auto_register(proposal, config)
            registered = {str(entry["cupon_id"]) for entry in auto_results if entry.get("ok")}
            proposal["matches_unicos"] = [
                match
                for match in proposal["matches_unicos"]
                if str(match["cupon"].get("cupon_id")) not in registered
            ]

        ready = [match for match in proposal["matches_unicos"] if match.get("can_confirm")]
        # Las facturas ya pagadas se muestran para explicar el cupon, pero no son
        # trabajo pendiente: no confundirlas con diferencias de importe.
        already_paid = [
            match for match in proposal["matches_unicos"]
            if not (match.get("invoice") or {}).get("can_register_payment")
        ]
        with_difference = [
            match for match in proposal["matches_unicos"]
            if not match.get("can_confirm") and (match.get("invoice") or {}).get("can_register_payment")
        ]
        ambiguous = proposal.get("ambiguos", [])
        summary = {
            "generated_at": _utc_now_iso(),
            "date_from": proposal["date_from"],
            "date_to": proposal["date_to"],
            "total_cupones": proposal["total_cupones"],
            "listos_para_revisar": len(ready),
            "con_diferencia": len(with_difference),
            "ya_pagadas": len(already_paid),
            "ambiguos": len(ambiguous),
            "sin_match": len(proposal.get("sin_match", [])),
            "registrados_automaticamente": sum(1 for entry in auto_results if entry.get("ok")),
            "errores_registro_automatico": sum(1 for entry in auto_results if not entry.get("ok")),
        }

        with self._lock:
            notified = {str(item) for item in self.state.get("notified_cupon_ids", [])}
            pending_ids = {
                str(row["cupon"].get("cupon_id"))
                for row in ready + ambiguous
                if row.get("cupon", {}).get("cupon_id") is not None
            }
            new_ids = pending_ids - notified
            summary["nuevos_para_revisar"] = len(new_ids)
            self.state["last_proposal"] = proposal
            self.state["notified_cupon_ids"] = sorted(notified | new_ids)[-MAX_NOTIFIED_IDS:]
            self._push_event(
                f"Sincronizado {summary['date_from']} a {summary['date_to']}: "
                f"{summary['listos_para_revisar']} listos, {summary['ambiguos']} ambiguos, "
                f"{summary['sin_match']} sin match, {summary['registrados_automaticamente']} registrados"
            )

        if config.get("auto_sync_notify_desktop", True) and (new_ids or summary["registrados_automaticamente"]):
            parts = []
            if new_ids:
                parts.append(f"{len(new_ids)} pagos nuevos listos para revisar")
            if summary["registrados_automaticamente"]:
                parts.append(f"{summary['registrados_automaticamente']} registrados automaticamente")
            self._notify("Conciliacion POS", ". ".join(parts))
        return summary

    # ---- worker ----
    def _is_due(self, config: Dict[str, Any]) -> bool:
        last = self.state.get("last_cycle_started_at")
        if not last:
            return True
        try:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
        except ValueError:
            return True
        return elapsed >= self._schedule(config)["interval_minutes"] * 60

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="pos-reconciliation-worker", daemon=True)
        self._thread.start()
        logger.info("Worker de conciliacion POS iniciado")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        self._stop_event.wait(45)
        while not self._stop_event.is_set():
            try:
                config = recon.load_recon_config()
                if config.get("auto_sync_enabled") and self._is_due(config):
                    self.run_cycle()
            except Exception as exc:
                logger.exception("Error inesperado en worker de conciliacion POS: %s", exc)
            self._stop_event.wait(60)


pos_reconciliation_worker = PosReconciliationWorker()
