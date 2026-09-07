"""
Integracion Odoo (XML-RPC + descarga de reportes PDF) para flujo de expedicion.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import time
import xmlrpc.client
import base64
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class OdooIntegration:
    _MAX_PUBLIC_ERROR_LEN = 280

    def __init__(self) -> None:
        self.config_path = self._resolve_config_path()
        self.config = self._load_config()

    @staticmethod
    def _collapse_whitespace(text: Any) -> str:
        raw = str(text or "")
        return " ".join(raw.replace("\r", " ").replace("\n", " ").split()).strip()

    @classmethod
    def _truncate_public_error(cls, message: str) -> str:
        compact = cls._collapse_whitespace(message)
        if not compact:
            return ""
        if len(compact) <= cls._MAX_PUBLIC_ERROR_LEN:
            return compact
        return f"{compact[:cls._MAX_PUBLIC_ERROR_LEN - 3]}..."

    def _humanize_fault(self, exc: xmlrpc.client.Fault) -> str:
        fault_text = str(getattr(exc, "faultString", "") or "")

        if "InFailedSqlTransaction" in fault_text:
            return (
                "Odoo no pudo confirmar la orden por un error de transaccion en stock/procurement. "
                "Revisa el log del servidor para ver la causa inicial."
            )

        match = re.search(
            r"(?:odoo\.exceptions\.)?(UserError|ValidationError|AccessError|MissingError):\s*(.+)",
            fault_text,
        )
        if match:
            err_type = match.group(1)
            err_message = self._truncate_public_error(match.group(2))
            return f"Odoo {err_type}: {err_message}"

        db_match = re.search(r"psycopg2\.errors\.([A-Za-z0-9_]+):\s*(.+)", fault_text)
        if db_match:
            db_message = self._truncate_public_error(db_match.group(2))
            return f"Odoo error de base de datos ({db_match.group(1)}): {db_message}"

        lines = [line.strip() for line in fault_text.splitlines() if line.strip()]
        for line in reversed(lines):
            if line.lower().startswith("traceback"):
                continue
            if line.startswith("File "):
                continue
            if line.startswith("return ") or line.startswith("res = ") or line.startswith("result = "):
                continue
            short_line = self._truncate_public_error(line)
            if short_line:
                return f"Odoo XML-RPC error: {short_line}"

        fallback = self._truncate_public_error(str(exc))
        return fallback or "Error XML-RPC de Odoo"

    def humanize_exception(self, exc: Exception) -> str:
        if isinstance(exc, xmlrpc.client.Fault):
            return self._humanize_fault(exc)

        message = str(exc or "")
        if "InFailedSqlTransaction" in message:
            return (
                "Odoo devolvio una transaccion abortada (InFailedSqlTransaction). "
                "Revisa el log del servidor para la causa inicial."
            )

        compact = self._truncate_public_error(message)
        return compact or "Error inesperado al comunicarse con Odoo"

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
            "order_pdf_render_dpi": 300,
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
            "order_spooler_timeout_seconds": 15,
            "order_spooler_poll_interval_seconds": 1,
            "order_print_submit_retries": 1,
            "order_strict_spooler_confirmation": False,
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
        include_all_states: bool = False,
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

        if states and not include_all_states:
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

    @staticmethod
    def _normalize_shipment_field_value(raw_value: Any) -> str:
        if raw_value is None:
            return ""
        if isinstance(raw_value, (list, tuple)):
            if len(raw_value) >= 2:
                second = str(raw_value[1] or "").strip()
                if second:
                    return second
            if len(raw_value) >= 1:
                first = str(raw_value[0] or "").strip()
                if first:
                    return first
            return ""
        return str(raw_value).strip()

    def get_cancelled_envio_ids(
        self,
        envio_ids: List[str],
        auth_override: Optional[Dict[str, str]] = None,
    ) -> set[str]:
        normalized_envios: List[str] = []
        seen: set[str] = set()
        for envio_id in envio_ids or []:
            envio = str(envio_id or "").strip()
            if not envio or envio in seen:
                continue
            normalized_envios.append(envio)
            seen.add(envio)

        if not normalized_envios:
            return set()

        runtime = self._build_runtime_config(auth_override)
        shipment_field = str(runtime.get("shipment_field", "")).strip()

        # Fallback compatible: si no hay campo de envio configurado, mantenemos lookup individual.
        if not shipment_field:
            cancelled: set[str] = set()
            for envio in normalized_envios:
                order = self.find_sale_order_by_envio(
                    envio,
                    auth_override=auth_override,
                    include_all_states=True,
                )
                if order and str(order.get("state") or "").strip().lower() == "cancel":
                    cancelled.add(envio)
            return cancelled

        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        orders = models.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "search_read",
            [[(shipment_field, "in", normalized_envios), ("state", "=", "cancel")]],
            {
                "fields": ["id", "state", shipment_field],
                "limit": max(200, len(normalized_envios) * 10),
                "order": "write_date desc, id desc",
            },
        )

        cancelled = set()
        normalized_set = set(normalized_envios)
        for order in orders or []:
            envio_value = self._normalize_shipment_field_value(order.get(shipment_field))
            if envio_value and envio_value in normalized_set:
                cancelled.add(envio_value)
        return cancelled

    def find_invoiced_sales(
        self,
        date_from: str = "",
        date_to: str = "",
        limit: Optional[int] = None,
        auth_override: Optional[Dict[str, str]] = None,
        only_pending: bool = False,
        only_cash_payment_term: bool = False,
    ) -> List[Dict[str, Any]]:
        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        date_from_value = str(date_from or "").strip()
        date_to_value = str(date_to or "").strip()
        if date_from_value and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from_value):
            raise ValueError("date_from debe usar formato YYYY-MM-DD")
        if date_to_value and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to_value):
            raise ValueError("date_to debe usar formato YYYY-MM-DD")

        limit_value = None
        if limit is not None:
            try:
                limit_value = int(limit)
            except (TypeError, ValueError):
                limit_value = None
            if limit_value is not None and limit_value <= 0:
                limit_value = None

        return self._search_invoices(
            date_from_value,
            date_to_value,
            limit_value,
            auth_override=auth_override,
            only_pending=only_pending,
            only_cash_payment_term=only_cash_payment_term,
        )

    def _search_invoices(
        self,
        date_from_value: str,
        date_to_value: str,
        limit_value: Optional[int],
        auth_override: Optional[Dict[str, str]] = None,
        only_pending: bool = False,
        only_cash_payment_term: bool = False,
    ) -> List[Dict[str, Any]]:
        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        invoice_date_fields = ["invoice_date", "date_invoice"]
        payment_state_fields = ["invoice_payment_state", "payment_state"]
        payment_term_fields = ["invoice_payment_term_id", "payment_term_id"]
        origin_fields = ["invoice_origin", "origin"]
        untaxed_fields = ["amount_untaxed"]

        available_fields = models.execute_kw(
            db,
            uid,
            password,
            "account.move",
            "fields_get",
            [[], ["string"]],
        ) or {}

        invoice_date_field = next((f for f in invoice_date_fields if f in available_fields), None)
        payment_state_field = next((f for f in payment_state_fields if f in available_fields), None)
        payment_term_field = next((f for f in payment_term_fields if f in available_fields), None)
        origin_field = next((f for f in origin_fields if f in available_fields), None)
        untaxed_field = next((f for f in untaxed_fields if f in available_fields), None)

        if not invoice_date_field:
            raise ValueError(
                "No se pudo obtener las facturas: verifica que el modelo account.move tenga fecha de factura."
            )

        try:
            domain: List[Any] = [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("reversal_move_id", "=", False),
            ]
            if date_from_value:
                domain.append((invoice_date_field, ">=", date_from_value))
            if date_to_value:
                domain.append((invoice_date_field, "<=", date_to_value))
            if only_pending:
                if not payment_state_field:
                    raise ValueError(
                        "No se pudo filtrar por facturas pendientes: el modelo account.move "
                        "no expone un campo de estado de pago en esta instancia de Odoo."
                    )
                domain.append((payment_state_field, "in", ["not_paid", "partial"]))
            if only_cash_payment_term:
                if not payment_term_field:
                    raise ValueError(
                        "No se pudo filtrar facturas a contado: Odoo no expone el campo de condicion de pago."
                    )
                cash_term_ids = self._find_cash_payment_term_ids(models, db, uid, password)
                if not cash_term_ids:
                    raise ValueError(
                        "No se encontro en Odoo una condicion de pago a contado "
                        "(Contado/Immediate Payment/Pago inmediato)."
                    )
                domain.append((payment_term_field, "in", cash_term_ids))

            fields = [
                "id",
                "name",
                "partner_id",
                "amount_total",
                "currency_id",
                invoice_date_field,
            ]
            if "amount_residual" in available_fields:
                fields.append("amount_residual")
            if payment_term_field:
                fields.append(payment_term_field)
            if untaxed_field:
                fields.append(untaxed_field)
            if payment_state_field:
                fields.append(payment_state_field)
            if origin_field:
                fields.append(origin_field)

            params: Dict[str, Any] = {
                "fields": fields,
                "order": f"{invoice_date_field} desc, id desc",
            }
            if limit_value is not None:
                params["limit"] = limit_value

            invoices = models.execute_kw(
                db,
                uid,
                password,
                "account.move",
                "search_read",
                [domain],
                params,
            )

            invoices_list = invoices or []
            for invoice in invoices_list:
                if invoice_date_field != "invoice_date":
                    invoice["invoice_date"] = invoice.get("date_invoice")
                    invoice.pop("date_invoice", None)
                if untaxed_field and untaxed_field != "amount_untaxed":
                    invoice["amount_untaxed"] = invoice.get(untaxed_field)
                    invoice.pop(untaxed_field, None)
                elif not untaxed_field:
                    invoice["amount_untaxed"] = ""
                if payment_state_field and payment_state_field != "invoice_payment_state":
                    invoice["invoice_payment_state"] = invoice.get(payment_state_field)
                    invoice.pop(payment_state_field, None)
                elif not payment_state_field:
                    invoice["invoice_payment_state"] = ""
                if payment_term_field and payment_term_field != "invoice_payment_term_id":
                    invoice["invoice_payment_term_id"] = invoice.get(payment_term_field)
                    invoice.pop(payment_term_field, None)
                if origin_field and origin_field != "invoice_origin":
                    invoice["invoice_origin"] = invoice.get(origin_field)
                    invoice.pop(origin_field, None)
            return invoices_list
        except Exception as exc:
            if isinstance(exc, xmlrpc.client.Fault):
                raise ValueError(
                    "No se pudo obtener las facturas: verifica que el modelo account.move tenga fecha de factura."
                )
            raise

    @staticmethod
    def _find_cash_payment_term_ids(
        models: Any,
        db: str,
        uid: int,
        password: str,
    ) -> List[int]:
        """Resuelve condiciones de contado por nombre, sin depender de IDs de una base."""
        terms = models.execute_kw(
            db,
            uid,
            password,
            "account.payment.term",
            "search_read",
            [[("active", "=", True)]],
            {"fields": ["id", "name"]},
        ) or []
        cash_names = {
            "contado",
            "immediate payment",
            "pago inmediato",
            "pago al contado",
        }
        return [
            int(term["id"])
            for term in terms
            if term.get("id") is not None
            and str(term.get("name") or "").strip().casefold() in cash_names
        ]

    def _web_auth_session(self, auth_override: Optional[Dict[str, str]] = None) -> httpx.Client:
        runtime = self._build_runtime_config(auth_override)
        session = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
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
        report_url = f"{self._base_url(runtime)}/report/pdf/{selected_report}/{int(order_id)}"
        session = self._web_auth_session(auth_override=auth_override)
        try:
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
        finally:
            session.close()

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
            try:
                models.execute_kw(
                    db,
                    uid,
                    password,
                    "sale.order",
                    "action_confirm",
                    [[int(order_id)]],
                )
            except Exception as exc:
                logger.exception("Error confirmando sale.order id=%s", order_id)
                raise ValueError(self.humanize_exception(exc)) from exc

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
        mapping = self.config.get("operator_odoo_users") or {}
        if not isinstance(mapping, dict):
            return None

        def _entry_to_auth(entry: Any) -> Optional[Dict[str, str]]:
            if not isinstance(entry, dict):
                return None
            odoo_user = str(entry.get("odoo_username") or "").strip()
            odoo_pass = str(entry.get("odoo_password") or "").strip()
            if not odoo_user or not odoo_pass:
                return None
            return {"username": odoo_user, "password": odoo_pass}

        if app_key:
            direct_entry = mapping.get(app_key)
            direct_auth = _entry_to_auth(direct_entry)
            if direct_auth:
                return direct_auth

            for stored_key, entry in mapping.items():
                normalized_key = str(stored_key or "").strip().lower()
                if normalized_key != app_key:
                    continue
                return _entry_to_auth(entry)

        # Fallback de compatibilidad: si hay un unico usuario Odoo valido cargado,
        # usarlo aunque no coincida el operador local.
        valid_auth = [_entry_to_auth(entry) for entry in mapping.values()]
        valid_auth = [item for item in valid_auth if item]
        if len(valid_auth) == 1:
            return valid_auth[0]

        return None

    def resolve_operator_auth_exact(self, app_username: str) -> Optional[Dict[str, str]]:
        """Resuelve un operador exacto, sin el fallback historico de usuario unico."""
        app_key = str(app_username or "").strip().lower()
        if not app_key:
            return None
        mapping = self.config.get("operator_odoo_users") or {}
        if not isinstance(mapping, dict):
            return None

        entry = mapping.get(app_key)
        if entry is None:
            for stored_key, stored_entry in mapping.items():
                if str(stored_key or "").strip().lower() == app_key:
                    entry = stored_entry
                    break
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

        def _as_int(value: Any, default: int, min_value: int, max_value: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                parsed = default
            if parsed < min_value:
                return min_value
            if parsed > max_value:
                return max_value
            return parsed

        def _as_float(value: Any, default: float, min_value: float, max_value: float) -> float:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                parsed = default
            if parsed < min_value:
                return min_value
            if parsed > max_value:
                return max_value
            return parsed

        def _extract_job_ids(items: List[Dict[str, Any]]) -> set[str]:
            return {str(job.get("job_id")) for job in items if job.get("job_id") is not None}

        def _add_stage(stage: str, status: str, message: str = "", **extra: Any) -> None:
            stage_event: Dict[str, Any] = {
                "stage": stage,
                "status": status,
                "at": time.time(),
            }
            if message:
                stage_event["message"] = message
            stage_event.update(extra)
            stage_timeline.append(stage_event)

        selected_printer = (printer or self.config.get("default_order_printer") or "").strip()
        if not selected_printer:
            raise ValueError("No hay impresora configurada para orden de Odoo")

        safe_copies = int(copies or self.config.get("default_order_copies") or 1)
        if safe_copies < 1:
            safe_copies = 1

        stage_timeline: List[Dict[str, Any]] = []
        spooler_max_jobs = 20
        confirmation_timeout_seconds = _as_int(
            self.config.get("order_spooler_timeout_seconds", 15),
            default=15,
            min_value=3,
            max_value=120,
        )
        poll_interval_seconds = _as_float(
            self.config.get("order_spooler_poll_interval_seconds", 1),
            default=1,
            min_value=0.3,
            max_value=5,
        )
        submit_retries = _as_int(
            self.config.get("order_print_submit_retries", 1),
            default=1,
            min_value=0,
            max_value=3,
        )
        strict_confirmation = bool(self.config.get("order_strict_spooler_confirmation", False))

        spooler_checked = True
        spooler_error = ""
        jobs_before: List[Dict[str, Any]] = []
        before_ids: set[str] = set()
        try:
            jobs_before = get_print_jobs_from_spooler(selected_printer, max_jobs=spooler_max_jobs)
            before_ids = _extract_job_ids(jobs_before)
            _add_stage(
                "snapshot_before",
                "ok",
                jobs_before=len(jobs_before),
                before_job_ids=sorted(before_ids),
            )
        except Exception as exc:
            spooler_checked = False
            spooler_error = str(exc)
            _add_stage("snapshot_before", "error", message=spooler_error)

        submission_success = False
        submission_error = ""
        submit_attempts = submit_retries + 1

        with tempfile.TemporaryDirectory(prefix="odoo_order_pdf_") as temp_dir:
            temp_path = Path(temp_dir)
            history_dir = temp_path / "historial"
            history_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = temp_path / f"odoo_order_{envio_id}.pdf"
            pdf_path.write_bytes(pdf_bytes)

            for attempt in range(1, submit_attempts + 1):
                _add_stage(
                    "submit_to_printer",
                    "started",
                    attempt=attempt,
                    total_attempts=submit_attempts,
                    printer=selected_printer,
                )
                handler = PDFHandler(
                    {
                        "entrada": str(temp_path),
                        "historial": str(history_dir),
                        "impresora": selected_printer,
                        "recortar_pdf": False,
                        "force_grayscale": bool(self.config.get("force_order_grayscale", False)),
                        "copias": safe_copies,
                        "pdf_render_dpi": int(self.config.get("order_pdf_render_dpi", 300) or 300),
                        "poppler": "",
                    },
                    observer=None,
                    root=None,
                )
                try:
                    attempt_ok = bool(handler.procesar_pdf(str(pdf_path)))
                except Exception as exc:
                    attempt_ok = False
                    submission_error = str(exc)
                    _add_stage(
                        "submit_to_printer",
                        "error",
                        message=submission_error,
                        attempt=attempt,
                    )
                finally:
                    handler.shutdown()

                if attempt_ok:
                    submission_success = True
                    submission_error = ""
                    _add_stage("submit_to_printer", "ok", attempt=attempt)
                    break

                if not submission_error:
                    submission_error = "PDFHandler no confirmo envio al spooler."
                if attempt < submit_attempts:
                    _add_stage(
                        "submit_to_printer",
                        "retry",
                        message=submission_error,
                        attempt=attempt,
                    )
                    time.sleep(1)
                else:
                    _add_stage(
                        "submit_to_printer",
                        "failed",
                        message=submission_error,
                        attempt=attempt,
                    )

        jobs_after: List[Dict[str, Any]] = jobs_before
        after_ids: set[str] = set(before_ids)
        new_job_ids: List[str] = []
        spooler_polls = 0
        waited_seconds = 0.0

        if submission_success and spooler_checked:
            _add_stage(
                "confirm_spooler",
                "started",
                timeout_seconds=confirmation_timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            deadline = time.time() + confirmation_timeout_seconds
            while time.time() <= deadline:
                spooler_polls += 1
                try:
                    jobs_after = get_print_jobs_from_spooler(selected_printer, max_jobs=spooler_max_jobs)
                    after_ids = _extract_job_ids(jobs_after)
                    new_job_ids = sorted(after_ids - before_ids)
                    waited_seconds = max(0.0, confirmation_timeout_seconds - max(0.0, deadline - time.time()))
                    if new_job_ids:
                        _add_stage(
                            "confirm_spooler",
                            "ok",
                            new_job_ids=new_job_ids,
                            polls=spooler_polls,
                            waited_seconds=round(waited_seconds, 2),
                        )
                        break
                except Exception as exc:
                    spooler_checked = False
                    spooler_error = str(exc)
                    _add_stage("confirm_spooler", "error", message=spooler_error, polls=spooler_polls)
                    break
                time.sleep(poll_interval_seconds)

            if spooler_checked and not new_job_ids:
                _add_stage(
                    "confirm_spooler",
                    "timeout",
                    polls=spooler_polls,
                    waited_seconds=round(waited_seconds, 2),
                )
        elif submission_success:
            _add_stage("confirm_spooler", "skipped", message="Spooler no disponible para confirmar")
        else:
            _add_stage("confirm_spooler", "skipped", message="No se confirma spooler por fallo de envio local")

        confirmation_state = "failed_submission"
        if submission_success:
            if new_job_ids:
                confirmation_state = "confirmed"
            elif spooler_checked:
                confirmation_state = "timeout_unconfirmed"
            else:
                confirmation_state = "unverified_spooler_unavailable"

        overall_success = bool(submission_success)
        if strict_confirmation and not new_job_ids:
            overall_success = False

        error_message = ""
        if not submission_success:
            error_message = submission_error or "No se pudo enviar el PDF a la impresora."
        elif strict_confirmation and not new_job_ids:
            error_message = (
                "Impresion enviada localmente pero no confirmada en spooler "
                f"({confirmation_state})."
            )

        return {
            "envio_id": envio_id,
            "printer": selected_printer,
            "success": overall_success,
            "local_submission_ok": bool(submission_success),
            "confirmation_state": confirmation_state,
            "strict_confirmation_enabled": strict_confirmation,
            "error": error_message,
            "verification": {
                "spooler_checked": spooler_checked,
                "spooler_error": spooler_error,
                "jobs_before": len(jobs_before),
                "jobs_after": len(jobs_after),
                "new_job_detected": bool(new_job_ids),
                "new_job_ids": new_job_ids,
                "confirmation_timeout_seconds": confirmation_timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
                "polls": spooler_polls,
                "waited_seconds": round(waited_seconds, 2),
                "submit_attempts": submit_attempts,
                "stages": stage_timeline,
            },
        }

    def get_payment_journals(
        self,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Lista los diarios contables de tipo banco/caja, para mapear POS -> diario."""
        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        journals = models.execute_kw(
            db,
            uid,
            password,
            "account.journal",
            "search_read",
            [[("type", "in", ["bank", "cash"])]],
            {"fields": ["id", "name", "type", "currency_id"], "order": "name"},
        )
        return journals or []

    def get_rounding_accounts(
        self,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Lista cuentas activas destinadas a diferencias de redondeo/cobro."""
        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        accounts = models.execute_kw(
            runtime.get("database", ""),
            uid,
            runtime.get("password", ""),
            "account.account",
            "search_read",
            [[("deprecated", "=", False), ("name", "ilike", "redonde")]],
            {
                "fields": ["id", "code", "name", "account_type", "currency_id"],
                "order": "code, name",
                "limit": 100,
            },
        )
        return accounts or []

    def attach_totalnet_receipt_to_payment(
        self,
        payment_id: int,
        filename: str,
        pdf_bytes: bytes,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Adjunta el PDF del comprobante TotalNet al pago, sin duplicar por nombre."""
        if not payment_id or not pdf_bytes:
            raise ValueError("Faltan datos para adjuntar el comprobante TotalNet")
        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        attachment_ids = models.execute_kw(
            db,
            uid,
            password,
            "ir.attachment",
            "search",
            [[
                ("res_model", "=", "account.payment"),
                ("res_id", "=", int(payment_id)),
                ("name", "=", str(filename)),
            ]],
            {"limit": 1},
        ) or []
        attachment_created = False
        if attachment_ids:
            attachment_id = int(attachment_ids[0])
        else:
            attachment_id = int(
                models.execute_kw(
                    db,
                    uid,
                    password,
                    "ir.attachment",
                    "create",
                    [{
                        "name": str(filename),
                        "type": "binary",
                        "datas": base64.b64encode(pdf_bytes).decode("ascii"),
                        "mimetype": "application/pdf",
                        "res_model": "account.payment",
                        "res_id": int(payment_id),
                    }],
                )
            )
            attachment_created = True

        return {
            "attachment_id": attachment_id,
            "attachment_created": attachment_created,
            "filename": str(filename),
        }

    def register_invoice_payment(
        self,
        invoice_id: int,
        amount: float,
        payment_date: str,
        journal_id: int,
        memo: str = "",
        auth_override: Optional[Dict[str, str]] = None,
        require_exact_invoice_total: bool = False,
        rounding_account_id: Optional[int] = None,
        rounding_source_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Registra un pago contra una factura via el wizard account.payment.register.

        Es el mismo mecanismo que usa el boton "Registrar pago" de la interfaz de Odoo.
        """
        if not invoice_id:
            raise ValueError("invoice_id invalido")
        if not journal_id:
            raise ValueError("journal_id invalido")
        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            raise ValueError("amount invalido")
        if amount_value <= 0:
            raise ValueError("amount debe ser mayor a 0")

        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        available_fields = models.execute_kw(
            db,
            uid,
            password,
            "account.move",
            "fields_get",
            [[], ["string"]],
        ) or {}
        payment_state_field = next(
            (name for name in ("invoice_payment_state", "payment_state") if name in available_fields),
            None,
        )
        if not payment_state_field:
            raise ValueError("Odoo no expone el estado de pago de la factura")
        invoice_read_fields = ["id", "name", "amount_total", payment_state_field]
        if "amount_residual" in available_fields:
            invoice_read_fields.append("amount_residual")
        before_data = models.execute_kw(
            db,
            uid,
            password,
            "account.move",
            "read",
            [[int(invoice_id)]],
            {"fields": invoice_read_fields},
        )
        if not before_data:
            raise ValueError("La factura indicada no existe en Odoo")
        payment_state_before = str(before_data[0].get(payment_state_field) or "")
        if payment_state_before not in {"not_paid", "partial"}:
            raise ValueError(
                "No se puede registrar otro pago: la factura ya figura como "
                f"'{payment_state_before or 'estado desconocido'}' en Odoo."
            )
        try:
            invoice_due = float(
                before_data[0].get("amount_residual")
                if before_data[0].get("amount_residual") is not None
                else before_data[0].get("amount_total")
            )
        except (TypeError, ValueError):
            raise ValueError("Odoo no devolvio el total pendiente de la factura")
        if require_exact_invoice_total:
            difference = round(invoice_due - amount_value, 2)
            if rounding_source_amount is not None:
                try:
                    source_amount = float(rounding_source_amount)
                    expected_rounded = float(
                        Decimal(str(invoice_due)).quantize(
                            Decimal("1"), rounding=ROUND_HALF_UP
                        )
                    )
                except (InvalidOperation, TypeError, ValueError):
                    raise ValueError("No se pudo validar el redondeo del pago")
                source_matches_invoice = round(source_amount - invoice_due, 2) == 0
                source_matches_rounded = round(source_amount - expected_rounded, 2) == 0
                if not (source_matches_invoice or source_matches_rounded):
                    raise ValueError(
                        "El importe TotalNet no corresponde al total Odoo ni a su "
                        "redondeo al peso. No se registro el pago."
                    )
                if round(amount_value - expected_rounded, 2) != 0:
                    raise ValueError(
                        "El importe del pago no usa el redondeo esperado por Odoo."
                    )
            if difference != 0:
                if not rounding_account_id or abs(difference) > 0.50:
                    raise ValueError(
                        "El importe de TotalNet no coincide con el total de la factura "
                        f"(pago: {amount_value:.2f}; Odoo: {invoice_due:.2f}; "
                        f"diferencia: {difference:+.2f}). No se registro el pago."
                    )

        payment_values: Dict[str, Any] = {
            "amount": amount_value,
            "journal_id": int(journal_id),
        }
        if payment_date:
            payment_values["payment_date"] = payment_date
        if memo:
            payment_values["communication"] = memo
        if rounding_account_id and round(invoice_due - amount_value, 2) != 0:
            payment_values.update(
                {
                    "payment_difference_handling": "reconcile",
                    "writeoff_account_id": int(rounding_account_id),
                    "writeoff_label": "Redondeo cobro POS TotalNet",
                }
            )

        try:
            wizard_id = models.execute_kw(
                db,
                uid,
                password,
                "account.payment.register",
                "create",
                [payment_values],
                {"context": {"active_model": "account.move", "active_ids": [int(invoice_id)]}},
            )
            result = models.execute_kw(
                db,
                uid,
                password,
                "account.payment.register",
                "action_create_payments",
                [[wizard_id]],
            )
        except Exception as exc:
            logger.exception("Error registrando pago para invoice_id=%s", invoice_id)
            raise ValueError(self.humanize_exception(exc)) from exc

        after_data = models.execute_kw(
            db,
            uid,
            password,
            "account.move",
            "read",
            [[int(invoice_id)]],
            {"fields": ["id", "name", payment_state_field]},
        )
        invoice_after = after_data[0] if after_data else {}

        payment_id = None
        try:
            payment_records = models.execute_kw(
                db,
                uid,
                password,
                "account.payment",
                "search_read",
                [[("reconciled_invoice_ids", "in", [int(invoice_id)])]],
                {"fields": ["id"], "order": "id desc", "limit": 1},
            )
            if payment_records:
                payment_id = int(payment_records[0]["id"])
        except Exception as exc:
            logger.warning(
                "No se pudo determinar el pago creado para invoice_id=%s: %s", invoice_id, exc
            )

        return {
            "invoice_id": int(invoice_id),
            "payment_id": payment_id,
            "wizard_id": wizard_id,
            "action_result": result,
            "payment_state": invoice_after.get(payment_state_field),
            "actor_username": str(runtime.get("username") or ""),
        }


odoo_integration = OdooIntegration()
