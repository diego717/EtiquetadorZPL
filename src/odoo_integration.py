"""
Integracion Odoo (XML-RPC + descarga de reportes PDF) para flujo de expedicion.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
import xmlrpc.client
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class OdooIntegration:
    def __init__(self) -> None:
        self.config_path = self._resolve_config_path()
        self.config = self._load_config()

    def _resolve_config_path(self) -> Path:
        try:
            from config_manager import config_manager

            return Path(config_manager.get_config_directory()) / "odoo_config.json"
        except Exception:
            import os

            if os.name == "nt":
                base_dir = Path(os.environ.get("APPDATA", "."))
            else:
                base_dir = Path.home() / ".config"
            config_dir = base_dir / "EtiquetadorZPL"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / "odoo_config.json"

    def _default_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "base_url": "",
            "database": "",
            "username": "",
            "password": "",
            "report_name": "sale.report_saleorder",
            "order_prefix": "ML ",
            "shipment_field": "",
            "allowed_order_states": "draft,sent,sale",
            "default_order_printer": "Expedicion",
            "fallback_order_printer": "",
            "default_order_copies": 1,
            "force_order_grayscale": False,
            "default_label_printer": "",
            "fallback_label_printer": "",
            "default_label_copies": 1,
            "automation_enabled": False,
            "automation_interval_seconds": 60,
            "automation_sync_limit": 20,
            "automation_include_reprint": False,
            "automation_order_to_label_delay_seconds": 1,
            "confirm_order_on_print": False,
            "operator_odoo_users": {},
            "last_error": "",
        }

    def _load_config(self) -> Dict[str, Any]:
        config = self._default_config()
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                config.update(saved)
            except Exception as exc:
                logger.warning("No se pudo cargar configuracion Odoo: %s", exc)
        return config

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update(updates)
        if not isinstance(self.config.get("operator_odoo_users"), dict):
            self.config["operator_odoo_users"] = {}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle, indent=2, ensure_ascii=True)
        return self.get_public_config()

    def get_public_config(self) -> Dict[str, Any]:
        safe = dict(self.config)
        if safe.get("password"):
            safe["password"] = "***"
        safe_users = {}
        for app_user, data in (self.config.get("operator_odoo_users") or {}).items():
            if not isinstance(data, dict):
                continue
            safe_users[str(app_user)] = {
                "odoo_username": str(data.get("odoo_username") or "").strip(),
                "has_password": bool(str(data.get("odoo_password") or "").strip()),
            }
        safe["operator_odoo_users"] = safe_users
        safe["configured"] = self.is_configured()
        safe["config_path"] = str(self.config_path)
        return safe

    def is_configured(self) -> bool:
        return bool(
            self.config.get("base_url")
            and self.config.get("database")
            and self.config.get("username")
            and self.config.get("password")
        )

    def _build_runtime_config(self, auth_override: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        runtime = dict(self.config)
        if auth_override:
            for key in ("base_url", "database", "username", "password"):
                value = str(auth_override.get(key) or "").strip()
                if value:
                    runtime[key] = value
        return runtime

    def _base_url(self, runtime: Optional[Dict[str, Any]] = None) -> str:
        cfg = runtime or self.config
        base_url = (cfg.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("Falta base_url de Odoo")
        if not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
        return base_url

    def _xmlrpc_common(self, runtime: Optional[Dict[str, Any]] = None) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(f"{self._base_url(runtime)}/xmlrpc/2/common", allow_none=True)

    def _xmlrpc_models(self, runtime: Optional[Dict[str, Any]] = None) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(f"{self._base_url(runtime)}/xmlrpc/2/object", allow_none=True)

    def _authenticate(self, auth_override: Optional[Dict[str, str]] = None) -> int:
        runtime = self._build_runtime_config(auth_override)
        common = self._xmlrpc_common(runtime)
        db = runtime.get("database", "")
        username = runtime.get("username", "")
        password = runtime.get("password", "")
        uid = common.authenticate(db, username, password, {})
        if not uid:
            raise ValueError("No se pudo autenticar en Odoo (revisar URL/DB/usuario/clave)")
        return int(uid)

    def test_connection(self) -> Dict[str, Any]:
        uid = self._authenticate()
        common = self._xmlrpc_common()
        version = common.version()
        return {
            "ok": True,
            "uid": uid,
            "version": version,
            "base_url": self._base_url(),
        }

    def _parse_allowed_states(self) -> List[str]:
        raw = str(self.config.get("allowed_order_states", "draft,sent,sale"))
        states = [state.strip() for state in raw.split(",") if state.strip()]
        return states or ["draft", "sent", "sale"]

    def find_sale_order_by_envio(
        self,
        envio_id: str,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        envio = str(envio_id or "").strip()
        if not envio:
            raise ValueError("envio_id vacio")

        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        order_prefix = str(runtime.get("order_prefix", "ML "))
        shipment_field = str(runtime.get("shipment_field", "")).strip()
        states = self._parse_allowed_states()

        if shipment_field:
            domain: List[Any] = [(shipment_field, "=", envio)]
        else:
            domain = [
                "|",
                "|",
                ("name", "=", f"{order_prefix}{envio}"),
                ("client_order_ref", "ilike", envio),
                ("origin", "ilike", envio),
            ]

        if states:
            domain.append(("state", "in", states))

        fields = [
            "id",
            "name",
            "state",
            "partner_id",
            "amount_total",
            "currency_id",
            "date_order",
            "create_date",
        ]

        orders = models.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "search_read",
            [domain],
            {
                "fields": fields,
                "limit": 1,
                "order": "write_date desc, id desc",
            },
        )
        if not orders:
            return None
        return orders[0]

    def _web_auth_session(self, auth_override: Optional[Dict[str, str]] = None) -> requests.Session:
        runtime = self._build_runtime_config(auth_override)
        session = requests.Session()
        url = f"{self._base_url(runtime)}/web/session/authenticate"
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "db": runtime.get("database", ""),
                "login": runtime.get("username", ""),
                "password": runtime.get("password", ""),
            },
        }
        response = session.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        error = data.get("error")
        if error:
            error_data = error.get("data") or {}
            error_name = str(error_data.get("name", ""))
            message = str(error.get("message") or "Error autenticando sesion web en Odoo")
            if "AccessDenied" in error_name or "AccessDenied" in message:
                raise ValueError(
                    "Odoo rechazo la autenticacion web para reportes PDF. "
                    "Usa password de usuario (la API key suele funcionar en XML-RPC pero no en /web/session/authenticate)."
                )
            raise ValueError(f"Error autenticando sesion web en Odoo: {message}")

        result = data.get("result") or {}
        uid = result.get("uid")
        if not uid:
            raise ValueError("No se pudo autenticar sesion web en Odoo")
        return session

    def download_sale_order_report_pdf(
        self,
        order_id: int,
        report_name: str = "",
        auth_override: Optional[Dict[str, str]] = None,
    ) -> bytes:
        if not order_id:
            raise ValueError("order_id invalido")
        runtime = self._build_runtime_config(auth_override)
        selected_report = (report_name or self.config.get("report_name") or "sale.report_saleorder").strip()
        session = self._web_auth_session(auth_override=auth_override)
        report_url = f"{self._base_url(runtime)}/report/pdf/{selected_report}/{int(order_id)}"
        response = session.get(report_url, timeout=60)
        if response.status_code >= 400:
            raise ValueError(f"Odoo devolvio {response.status_code} al descargar reporte {selected_report}")
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
            preview = response.text[:250].replace("\n", " ").strip()
            raise ValueError(
                "La respuesta de Odoo no parece PDF. "
                f"Report={selected_report} Content-Type={content_type} Preview={preview}"
            )
        return response.content

    def confirm_sale_order(
        self,
        order_id: int,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        if not order_id:
            raise ValueError("order_id invalido")
        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        before_data = models.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "read",
            [[int(order_id)]],
            {"fields": ["id", "name", "state"]},
        )
        if not before_data:
            raise ValueError(f"No existe sale.order id={order_id}")

        state_before = str(before_data[0].get("state") or "")
        if state_before not in {"sale", "done", "cancel"}:
            models.execute_kw(
                db,
                uid,
                password,
                "sale.order",
                "action_confirm",
                [[int(order_id)]],
            )

        after_data = models.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "read",
            [[int(order_id)]],
            {"fields": ["id", "name", "state"]},
        )
        state_after = str((after_data[0] if after_data else {}).get("state") or "")
        return {
            "order_id": int(order_id),
            "state_before": state_before,
            "state_after": state_after,
            "confirmed": state_after in {"sale", "done"} and state_after != state_before,
            "actor_username": str(runtime.get("username", "")),
        }

    def get_operator_odoo_users_public(self) -> List[Dict[str, Any]]:
        users = []
        mapping = self.config.get("operator_odoo_users") or {}
        if not isinstance(mapping, dict):
            return users
        for app_username in sorted(mapping.keys()):
            item = mapping.get(app_username) or {}
            if not isinstance(item, dict):
                continue
            users.append(
                {
                    "app_username": str(app_username),
                    "odoo_username": str(item.get("odoo_username") or "").strip(),
                    "has_password": bool(str(item.get("odoo_password") or "").strip()),
                }
            )
        return users

    def set_operator_odoo_user(self, app_username: str, odoo_username: str, odoo_password: str) -> List[Dict[str, Any]]:
        app_key = str(app_username or "").strip().lower()
        odoo_user = str(odoo_username or "").strip()
        odoo_pass = str(odoo_password or "").strip()
        if not app_key:
            raise ValueError("app_username vacio")
        if not odoo_user:
            raise ValueError("odoo_username vacio")
        if not odoo_pass:
            raise ValueError("odoo_password vacio")

        mapping = self.config.get("operator_odoo_users")
        if not isinstance(mapping, dict):
            mapping = {}
        mapping[app_key] = {"odoo_username": odoo_user, "odoo_password": odoo_pass}
        self.save_config({"operator_odoo_users": mapping})
        return self.get_operator_odoo_users_public()

    def delete_operator_odoo_user(self, app_username: str) -> List[Dict[str, Any]]:
        app_key = str(app_username or "").strip().lower()
        if not app_key:
            raise ValueError("app_username vacio")
        mapping = self.config.get("operator_odoo_users")
        if not isinstance(mapping, dict):
            mapping = {}
        if app_key in mapping:
            mapping.pop(app_key, None)
            self.save_config({"operator_odoo_users": mapping})
        return self.get_operator_odoo_users_public()

    def resolve_operator_auth(self, app_username: str) -> Optional[Dict[str, str]]:
        app_key = str(app_username or "").strip().lower()
        if not app_key:
            return None
        mapping = self.config.get("operator_odoo_users") or {}
        if not isinstance(mapping, dict):
            return None
        entry = mapping.get(app_key) or {}
        if not isinstance(entry, dict):
            return None
        odoo_user = str(entry.get("odoo_username") or "").strip()
        odoo_pass = str(entry.get("odoo_password") or "").strip()
        if not odoo_user or not odoo_pass:
            return None
        return {"username": odoo_user, "password": odoo_pass}

    def print_order_pdf(
        self,
        pdf_bytes: bytes,
        envio_id: str,
        printer: str = "",
        copies: Optional[int] = None,
    ) -> Dict[str, Any]:
        from handlers import PDFHandler
        from print_queue_monitor import get_print_jobs_from_spooler

        selected_printer = (printer or self.config.get("default_order_printer") or "").strip()
        if not selected_printer:
            raise ValueError("No hay impresora configurada para orden de Odoo")

        safe_copies = int(copies or self.config.get("default_order_copies") or 1)
        if safe_copies < 1:
            safe_copies = 1

        jobs_before = get_print_jobs_from_spooler(selected_printer, max_jobs=10)
        before_ids = {str(job.get("job_id")) for job in jobs_before if job.get("job_id") is not None}

        with tempfile.TemporaryDirectory(prefix="odoo_order_pdf_") as temp_dir:
            temp_path = Path(temp_dir)
            history_dir = temp_path / "historial"
            history_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = temp_path / f"odoo_order_{envio_id}.pdf"
            pdf_path.write_bytes(pdf_bytes)

            handler = PDFHandler(
                {
                    "entrada": str(temp_path),
                    "historial": str(history_dir),
                    "impresora": selected_printer,
                    "recortar_pdf": False,
                    "force_grayscale": bool(self.config.get("force_order_grayscale", False)),
                    "copias": safe_copies,
                    "poppler": "",
                },
                observer=None,
                root=None,
            )
            try:
                success = handler.procesar_pdf(str(pdf_path))
            finally:
                handler.shutdown()

        time.sleep(2)
        jobs_after = get_print_jobs_from_spooler(selected_printer, max_jobs=10)
        after_ids = {str(job.get("job_id")) for job in jobs_after if job.get("job_id") is not None}
        new_job_ids = sorted(after_ids - before_ids)

        return {
            "envio_id": envio_id,
            "printer": selected_printer,
            "success": bool(success),
            "verification": {
                "spooler_checked": True,
                "jobs_before": len(jobs_before),
                "jobs_after": len(jobs_after),
                "new_job_detected": bool(new_job_ids),
                "new_job_ids": new_job_ids,
            },
        }


odoo_integration = OdooIntegration()
