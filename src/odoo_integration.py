"""
Integracion Odoo (XML-RPC + descarga de reportes PDF) para flujo de expedicion.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import tempfile
import threading
import time
import xmlrpc.client
import base64
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# El uid y la estructura de los modelos (fields_get) no cambian entre
# consultas: se guardan para no repetir esas llamadas en cada sincronizacion.
AUTH_CACHE_TTL_SECONDS = 15 * 60
FIELDS_GET_CACHE_TTL_SECONDS = 60 * 60
_metadata_cache_lock = threading.Lock()
_auth_cache: Dict[tuple, tuple] = {}
_fields_get_cache: Dict[tuple, tuple] = {}


def clear_metadata_cache() -> None:
    with _metadata_cache_lock:
        _auth_cache.clear()
        _fields_get_cache.clear()


def _cache_get(cache: Dict[tuple, tuple], key: tuple, ttl: float) -> Any:
    with _metadata_cache_lock:
        entry = cache.get(key)
    if entry is None or time.monotonic() - entry[0] > ttl:
        return None
    return copy.deepcopy(entry[1])


def _cache_set(cache: Dict[tuple, tuple], key: tuple, value: Any) -> None:
    with _metadata_cache_lock:
        cache[key] = (time.monotonic(), copy.deepcopy(value))


class _CachingModelsProxy:
    """Envuelve el proxy XML-RPC de Odoo y guarda las respuestas de fields_get."""

    def __init__(self, proxy: Any, base_url: str) -> None:
        self._proxy = proxy
        self._base_url = base_url

    def execute_kw(self, db: str, uid: int, password: str, model: str, method: str, *rest: Any) -> Any:
        if method != "fields_get":
            return self._proxy.execute_kw(db, uid, password, model, method, *rest)
        key = (self._base_url, db, uid, model, json.dumps(rest, sort_keys=True, default=str))
        cached = _cache_get(_fields_get_cache, key, FIELDS_GET_CACHE_TTL_SECONDS)
        if cached is not None:
            return cached
        result = self._proxy.execute_kw(db, uid, password, model, method, *rest)
        _cache_set(_fields_get_cache, key, result)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._proxy, name)


class OdooIntegration:
    _MAX_PUBLIC_ERROR_LEN = 280

    def __init__(self) -> None:
        self.config_path = self._resolve_config_path()
        self.config = self._load_config()
        # event_key de notas de impresion ya publicadas -> message_id (orden de insercion).
        self._posted_print_notes: Dict[str, Optional[int]] = {}

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
        clear_metadata_cache()
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

    def sale_order_url(self, order_id: int) -> str:
        """URL del formulario de la orden. Odoo 17+ redirige este formato clasico a su ruta nueva."""
        return f"{self._base_url()}/web#id={int(order_id)}&model=sale.order&view_type=form"

    def _xmlrpc_common(self, runtime: Optional[Dict[str, Any]] = None) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(f"{self._base_url(runtime)}/xmlrpc/2/common", allow_none=True)

    def _xmlrpc_models(self, runtime: Optional[Dict[str, Any]] = None) -> Any:
        base_url = self._base_url(runtime)
        proxy = xmlrpc.client.ServerProxy(f"{base_url}/xmlrpc/2/object", allow_none=True)
        return _CachingModelsProxy(proxy, base_url)

    def _authenticate(
        self,
        auth_override: Optional[Dict[str, str]] = None,
        use_cache: bool = True,
    ) -> int:
        runtime = self._build_runtime_config(auth_override)
        db = runtime.get("database", "")
        username = runtime.get("username", "")
        password = runtime.get("password", "")
        key = (
            self._base_url(runtime),
            db,
            username,
            hashlib.sha256(str(password).encode("utf-8")).hexdigest(),
        )
        if use_cache:
            cached = _cache_get(_auth_cache, key, AUTH_CACHE_TTL_SECONDS)
            if cached is not None:
                return cached
        common = self._xmlrpc_common(runtime)
        uid = common.authenticate(db, username, password, {})
        if not uid:
            raise ValueError("No se pudo autenticar en Odoo (revisar URL/DB/usuario/clave)")
        _cache_set(_auth_cache, key, int(uid))
        return int(uid)

    def test_connection(self) -> Dict[str, Any]:
        # Probar conexion siempre verifica contra Odoo, sin cache.
        uid = self._authenticate(use_cache=False)
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

    def find_sale_invoice_for_reference(
        self,
        sale_reference: str,
        amount: float,
        currency: str = "",
        auth_override: Optional[Dict[str, str]] = None,
        amount_tolerance: float = 0.01,
    ) -> Dict[str, Any]:
        """Busca una unica factura pendiente de una venta externa.

        La referencia se compara con el nombre esperado de la orden (por
        defecto ``ML <id>``), ``client_order_ref`` y ``origin``. Nunca elige
        una factura si la moneda difiere o el importe se aparta mas de
        ``amount_tolerance``.
        """
        reference = str(sale_reference or "").strip()
        if not reference:
            raise ValueError("Referencia de venta vacia")
        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            raise ValueError("Importe de venta invalido")
        if amount_value <= 0:
            raise ValueError("El importe de venta debe ser mayor a 0")

        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")
        expected_name = f"{str(runtime.get('order_prefix', 'ML '))}{reference}"

        sale_orders = models.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "search_read",
            [[
                "|",
                "|",
                ("name", "=", expected_name),
                ("client_order_ref", "ilike", reference),
                ("origin", "ilike", reference),
            ]],
            {
                "fields": ["id", "name", "client_order_ref", "origin", "invoice_ids"],
                "limit": 10,
                "order": "id desc",
            },
        ) or []
        exact_orders = [
            order for order in sale_orders
            if str(order.get("name") or "").strip().casefold() == expected_name.casefold()
        ]
        if len(exact_orders) == 1:
            sale_order = exact_orders[0]
        elif len(sale_orders) == 1:
            sale_order = sale_orders[0]
        elif len(sale_orders) > 1:
            return {
                "can_register": False,
                "reason": f"Hay varias ordenes Odoo relacionadas con Mercado Libre {reference}",
                "sale_order": None,
                "invoice": None,
            }
        else:
            return {
                "can_register": False,
                "reason": f"No se encontro la orden Odoo ML {reference}",
                "sale_order": None,
                "invoice": None,
            }

        invoice_ids = [int(item) for item in (sale_order.get("invoice_ids") or []) if item]
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

        domain: List[Any] = [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
        ]
        if "reversal_move_id" in available_fields:
            domain.append(("reversal_move_id", "=", False))
        if invoice_ids:
            domain.append(("id", "in", invoice_ids))
        else:
            origin_field = next(
                (name for name in ("invoice_origin", "origin") if name in available_fields),
                None,
            )
            if not origin_field:
                return {
                    "can_register": False,
                    "reason": f"La orden {sale_order.get('name')} no tiene facturas asociadas",
                    "sale_order": sale_order,
                    "invoice": None,
                }
            domain.append((origin_field, "ilike", str(sale_order.get("name") or expected_name)))

        fields = ["id", "name", "amount_total", "currency_id", payment_state_field]
        if "amount_residual" in available_fields:
            fields.append("amount_residual")
        invoices = models.execute_kw(
            db,
            uid,
            password,
            "account.move",
            "search_read",
            [domain],
            {"fields": fields, "order": "id desc", "limit": 20},
        ) or []

        expected_currency = str(currency or "").strip().casefold()
        exact_pending: List[Dict[str, Any]] = []
        exact_paid: List[Dict[str, Any]] = []
        pending: List[Dict[str, Any]] = []
        settled: List[Dict[str, Any]] = []
        for invoice in invoices:
            payment_state = str(invoice.get(payment_state_field) or "")
            invoice["invoice_payment_state"] = payment_state
            try:
                total_value = float(invoice.get("amount_total") or 0)
            except (TypeError, ValueError):
                total_value = 0.0
            due = invoice.get("amount_residual")
            try:
                due_value = total_value if due is None else float(due or 0)
            except (TypeError, ValueError):
                due_value = 0.0
            invoice["amount_due"] = round(due_value, 2)
            currency_value = invoice.get("currency_id")
            if isinstance(currency_value, (list, tuple)) and len(currency_value) > 1:
                invoice_currency = str(currency_value[1] or "")
            else:
                invoice_currency = str(currency_value or "")
            currency_matches = not expected_currency or invoice_currency.casefold() == expected_currency
            if payment_state in {"not_paid", "partial"}:
                pending.append(invoice)
                if round(abs(due_value - amount_value), 2) <= amount_tolerance and currency_matches:
                    exact_pending.append(invoice)
            else:
                # Una factura pagada tiene saldo 0: se compara contra su total.
                settled.append(invoice)
                if round(abs(total_value - amount_value), 2) <= amount_tolerance and currency_matches:
                    exact_paid.append(invoice)

        if len(exact_pending) == 1:
            return {
                "can_register": True,
                "reason": "",
                "sale_order": sale_order,
                "invoice": exact_pending[0],
            }
        if len(exact_pending) > 1:
            return {
                "can_register": False,
                "reason": "Hay varias facturas pendientes con el mismo importe y moneda",
                "sale_order": sale_order,
                "invoice": None,
            }
        if exact_paid:
            return {
                "can_register": False,
                "reason": "La factura relacionada ya tiene el pago registrado en Odoo",
                "sale_order": sale_order,
                "invoice": exact_paid[0],
            }
        if len(pending) == 1:
            invoice = pending[0]
            return {
                "can_register": False,
                "reason": (
                    "El importe o la moneda de Mercado Libre no coincide con la factura "
                    f"{invoice.get('name')} (pendiente: {invoice.get('amount_due')})"
                ),
                "sale_order": sale_order,
                "invoice": invoice,
            }
        if settled and not pending:
            invoice = settled[0]
            return {
                "can_register": False,
                "reason": (
                    f"La factura {invoice.get('name')} ya esta pagada, pero su total "
                    f"({invoice.get('amount_total')}) no coincide con Mercado Libre ({amount_value:.2f})"
                ),
                "sale_order": sale_order,
                "invoice": invoice,
            }
        if not invoices:
            return {
                "can_register": False,
                "reason": f"La orden {sale_order.get('name')} no tiene facturas publicadas",
                "sale_order": sale_order,
                "invoice": None,
            }
        return {
            "can_register": False,
            "reason": f"La orden {sale_order.get('name')} no tiene una factura pendiente compatible",
            "sale_order": sale_order,
            "invoice": pending[0] if pending else None,
        }

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

    def get_sale_order_stock_statuses(
        self,
        envio_ids: List[str],
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Resume en lote el estado de entrega/reserva para una lista de envios.

        Es una consulta estrictamente informativa: no reserva stock ni valida pickings.
        Usa campos opcionales cuando la version de Odoo los expone y degrada al estado
        de ``stock.picking`` cuando no existen los textos calculados de disponibilidad.
        """
        normalized_envios: List[str] = []
        seen: set[str] = set()
        for raw_envio in envio_ids or []:
            envio = str(raw_envio or "").strip()
            if not envio or envio in seen:
                continue
            normalized_envios.append(envio)
            seen.add(envio)

        if not normalized_envios:
            return {}

        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")
        order_prefix = str(runtime.get("order_prefix", "ML "))
        shipment_field = str(runtime.get("shipment_field", "")).strip()

        default_statuses: Dict[str, Dict[str, Any]] = {
            envio: {
                "code": "order_missing",
                "label": "Sin orden Odoo",
                "detail": "No se encontro una orden vinculada a este envio.",
                "order_id": None,
                "order_name": "",
                "order_state": "",
                "pickings": [],
            }
            for envio in normalized_envios
        }

        sale_fields = models.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "fields_get",
            [[], ["string"]],
        ) or {}
        available_sale_fields = set(sale_fields.keys())

        match_fields = [field for field in ("name", "client_order_ref", "origin") if field in available_sale_fields]
        if shipment_field and shipment_field not in available_sale_fields:
            logger.warning("Campo shipment Odoo no disponible al consultar stock: %s", shipment_field)
            shipment_field = ""

        if shipment_field:
            domain: List[Any] = [(shipment_field, "in", normalized_envios)]
        else:
            filters: List[Any] = []
            for envio in normalized_envios:
                if "name" in available_sale_fields:
                    filters.append(("name", "=", f"{order_prefix}{envio}"))
                if "client_order_ref" in available_sale_fields:
                    filters.append(("client_order_ref", "ilike", envio))
                if "origin" in available_sale_fields:
                    filters.append(("origin", "ilike", envio))
            domain = self._build_or_domain(filters)

        if not domain:
            return default_statuses

        order_fields = [field for field in ("id", "name", "state", "picking_ids") if field in available_sale_fields]
        for field in match_fields + ([shipment_field] if shipment_field else []):
            if field and field not in order_fields:
                order_fields.append(field)

        orders = models.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "search_read",
            [domain],
            {
                "fields": order_fields,
                "limit": max(200, len(normalized_envios) * 5),
                "order": "write_date desc, id desc",
            },
        ) or []

        orders_by_envio: Dict[str, Dict[str, Any]] = {}
        for envio in normalized_envios:
            expected_name = f"{order_prefix}{envio}".casefold()
            for order in orders:
                if shipment_field:
                    candidate = self._normalize_shipment_field_value(order.get(shipment_field))
                    matches = candidate == envio
                else:
                    name = str(order.get("name") or "").strip().casefold()
                    reference = str(order.get("client_order_ref") or "").strip().casefold()
                    origin = str(order.get("origin") or "").strip().casefold()
                    envio_folded = envio.casefold()
                    matches = name == expected_name or envio_folded in reference or envio_folded in origin
                if matches:
                    orders_by_envio[envio] = order
                    break

        order_ids = [int(order["id"]) for order in orders_by_envio.values() if order.get("id")]
        pickings: List[Dict[str, Any]] = []
        pickings_by_order: Dict[int, List[Dict[str, Any]]] = {order_id: [] for order_id in order_ids}
        moves_by_picking: Dict[int, List[Dict[str, Any]]] = {}
        picking_type_code_available = False

        if order_ids:
            picking_fields = models.execute_kw(
                db,
                uid,
                password,
                "stock.picking",
                "fields_get",
                [[], ["string"]],
            ) or {}
            available_picking_fields = set(picking_fields.keys())
            picking_type_code_available = "picking_type_code" in available_picking_fields
            wanted_picking_fields = (
                "id",
                "name",
                "state",
                "sale_id",
                "picking_type_code",
                "products_availability",
                "products_availability_state",
                "scheduled_date",
            )
            selected_picking_fields = [
                field for field in wanted_picking_fields if field in available_picking_fields
            ]

            picking_ids = sorted({
                int(picking_id)
                for order in orders_by_envio.values()
                for picking_id in (order.get("picking_ids") or [])
                if picking_id
            })
            if picking_ids:
                picking_domain: List[Any] = [("id", "in", picking_ids)]
            elif "sale_id" in available_picking_fields:
                picking_domain = [("sale_id", "in", order_ids)]
            else:
                picking_domain = []

            if picking_domain:
                pickings = models.execute_kw(
                    db,
                    uid,
                    password,
                    "stock.picking",
                    "search_read",
                    [picking_domain],
                    {
                        "fields": selected_picking_fields,
                        "order": "id asc",
                        "limit": max(200, len(order_ids) * 10),
                    },
                ) or []

            picking_by_id = {
                int(picking["id"]): picking
                for picking in pickings
                if picking.get("id")
            }
            for order in orders_by_envio.values():
                order_id = int(order["id"])
                linked_ids = [int(value) for value in (order.get("picking_ids") or []) if value]
                if linked_ids:
                    pickings_by_order[order_id] = [
                        picking_by_id[picking_id]
                        for picking_id in linked_ids
                        if picking_id in picking_by_id
                    ]
                    continue
                pickings_by_order[order_id] = [
                    picking
                    for picking in pickings
                    if self._many2one_parts(picking.get("sale_id"))[0] == order_id
                ]

            loaded_picking_ids = [int(picking["id"]) for picking in pickings if picking.get("id")]
            if loaded_picking_ids:
                move_fields = models.execute_kw(
                    db,
                    uid,
                    password,
                    "stock.move",
                    "fields_get",
                    [[], ["string"]],
                ) or {}
                available_move_fields = set(move_fields.keys())
                wanted_move_fields = (
                    "id",
                    "picking_id",
                    "product_id",
                    "product_uom_qty",
                    "product_uom",
                    "state",
                    "reserved_availability",
                    "quantity",
                    "picked",
                    "forecast_availability",
                )
                selected_move_fields = [
                    field for field in wanted_move_fields if field in available_move_fields
                ]
                moves = models.execute_kw(
                    db,
                    uid,
                    password,
                    "stock.move",
                    "search_read",
                    [[("picking_id", "in", loaded_picking_ids)]],
                    {
                        "fields": selected_move_fields,
                        "order": "picking_id asc, id asc",
                        "limit": max(500, len(loaded_picking_ids) * 50),
                    },
                ) or []
                for move in moves:
                    picking_id = self._many2one_parts(move.get("picking_id"))[0]
                    if picking_id is not None:
                        moves_by_picking.setdefault(picking_id, []).append(move)

        for envio, order in orders_by_envio.items():
            order_id = int(order.get("id") or 0)
            order_state = str(order.get("state") or "").strip().lower()
            order_pickings = pickings_by_order.get(order_id, [])
            outgoing_pickings = [
                picking
                for picking in order_pickings
                if str(picking.get("picking_type_code") or "").strip().lower() == "outgoing"
            ]
            relevant_pickings = (
                outgoing_pickings
                if picking_type_code_available
                else order_pickings
            )
            picking_states = [
                str(picking.get("state") or "").strip().lower()
                for picking in relevant_pickings
            ]
            active_states = [state for state in picking_states if state not in {"done", "cancel"}]
            availability_texts = []
            for picking in relevant_pickings:
                text = self._collapse_whitespace(picking.get("products_availability"))
                if text and text not in availability_texts:
                    availability_texts.append(text)

            relevant_moves = [
                move
                for picking in relevant_pickings
                for move in moves_by_picking.get(int(picking.get("id") or 0), [])
                if str(move.get("state") or "").strip().lower() not in {"done", "cancel"}
            ]
            shortages: List[Dict[str, Any]] = []
            demanded_qty = 0.0
            reserved_qty = 0.0
            reservation_known = bool(relevant_moves)
            complete_lines = 0
            uom_names: set[str] = set()
            for move in relevant_moves:
                try:
                    demand = max(0.0, float(move.get("product_uom_qty") or 0.0))
                except (TypeError, ValueError):
                    demand = 0.0

                if "reserved_availability" in move:
                    raw_reserved = move.get("reserved_availability")
                elif "quantity" in move:
                    # Odoo 17+ consolida la cantidad reservada/operada en ``quantity``.
                    raw_reserved = move.get("quantity")
                else:
                    raw_reserved = None
                    reservation_known = False

                try:
                    reserved = max(0.0, float(raw_reserved)) if raw_reserved is not None else 0.0
                except (TypeError, ValueError):
                    reserved = 0.0
                    reservation_known = False

                demanded_qty += demand
                reserved_qty += min(reserved, demand) if demand > 0 else reserved
                missing = max(0.0, demand - reserved)
                _uom_id, uom_name = self._many2one_parts(move.get("product_uom"))
                if uom_name:
                    uom_names.add(uom_name)
                if raw_reserved is not None and missing <= 0.00001:
                    complete_lines += 1
                if raw_reserved is not None and missing > 0.00001:
                    _product_id, product_name = self._many2one_parts(move.get("product_id"))
                    shortages.append(
                        {
                            "product": product_name or f"Producto {move.get('product_id') or '-'}",
                            "demanded_qty": demand,
                            "reserved_qty": reserved,
                            "missing_qty": missing,
                            "uom": uom_name,
                        }
                    )

            quantities_share_uom = len(uom_names) <= 1
            missing_qty = (
                max(0.0, demanded_qty - reserved_qty)
                if reservation_known and quantities_share_uom
                else None
            )

            if order_state == "cancel":
                code, label = "cancelled", "Orden cancelada"
                detail = "La orden de venta esta cancelada en Odoo."
            elif not relevant_pickings and order_state in {"draft", "sent"}:
                code, label = "quotation", "Cotizacion sin entrega"
                detail = "Odoo creara la entrega cuando se confirme la cotizacion."
            elif not relevant_pickings:
                code, label = "no_picking", "Sin entrega"
                detail = "La orden existe, pero todavia no tiene una entrega asociada."
            elif picking_states and all(state == "cancel" for state in picking_states):
                code, label = "cancelled", "Entrega cancelada"
                detail = "Las entregas asociadas estan canceladas."
            elif picking_states and all(state in {"done", "cancel"} for state in picking_states):
                code, label = "done", "Entrega realizada"
                detail = "La entrega ya fue validada en Odoo."
            elif reservation_known and relevant_moves and not shortages:
                code, label = "ready", "Stock reservado"
                detail = f"{complete_lines} de {len(relevant_moves)} lineas completamente reservadas."
            elif reservation_known and shortages and reserved_qty > 0:
                code, label = "partial", "Reserva parcial"
                detail = f"{complete_lines} de {len(relevant_moves)} lineas completamente reservadas."
            elif reservation_known and shortages:
                code, label = "waiting", "Pendiente de stock"
                detail = f"0 de {len(relevant_moves)} lineas completamente reservadas."
            elif active_states and all(state == "assigned" for state in active_states):
                code, label = "ready", "Entrega lista"
                detail = "Odoo informa que la entrega esta lista; no expone cantidades reservadas."
            elif "assigned" in active_states:
                code, label = "partial", "Reserva parcial"
                detail = "Hay entregas listas y otras aun pendientes; sin cantidades detalladas."
            elif "waiting" in active_states:
                code, label = "waiting_operation", "Esperando otra operacion"
                detail = "La entrega depende de un movimiento de stock anterior."
            elif "confirmed" in active_states:
                code, label = "waiting", "Pendiente de stock"
                detail = "Odoo aun no pudo reservar toda la mercaderia."
            else:
                code, label = "draft", "Entrega en borrador"
                detail = "La entrega existe, pero todavia no esta lista para reservar."

            if availability_texts:
                detail = f"{detail} Odoo: {' | '.join(availability_texts[:2])}"

            default_statuses[envio] = {
                "code": code,
                "label": label,
                "detail": detail,
                "order_id": order_id,
                "order_name": str(order.get("name") or ""),
                "order_state": order_state,
                "demanded_qty": demanded_qty if reservation_known and quantities_share_uom else None,
                "reserved_qty": reserved_qty if reservation_known and quantities_share_uom else None,
                "missing_qty": missing_qty,
                "complete_lines": complete_lines if reservation_known else None,
                "total_lines": len(relevant_moves) if reservation_known else None,
                "shortages": shortages,
                "pickings": [
                    {
                        "id": picking.get("id"),
                        "name": str(picking.get("name") or ""),
                        "state": str(picking.get("state") or ""),
                        "availability": self._collapse_whitespace(picking.get("products_availability")),
                        "availability_state": str(picking.get("products_availability_state") or ""),
                        "scheduled_date": picking.get("scheduled_date") or "",
                    }
                    for picking in relevant_pickings
                ],
            }

        return default_statuses

    def post_sale_order_print_note(
        self,
        order_id: int,
        envio_id: str,
        mode: str,
        order_printer: str = "",
        label_printer: str = "",
        event_key: str = "",
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Publica una nota de trazabilidad sin asignar responsable de preparacion."""
        if not order_id:
            raise ValueError("order_id invalido")

        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")
        safe_event_key = re.sub(r"[^A-Za-z0-9._:-]+", "-", str(event_key or "").strip())[:80]
        dedupe_key = f"{int(order_id)}:{safe_event_key}" if safe_event_key else ""

        # La idempotencia (reintentos de la misma operacion) se resuelve en
        # memoria para no ensuciar el chatter con una referencia tecnica.
        if dedupe_key and dedupe_key in self._posted_print_notes:
            return {
                "success": True,
                "posted": False,
                "duplicate": True,
                "order_id": int(order_id),
                "message_id": self._posted_print_notes[dedupe_key],
                "event_key": safe_event_key,
            }

        # Texto plano: por XML-RPC Odoo escapa el HTML del body y lo muestra literal.
        body = {
            "both": "Orden y etiqueta impresas",
            "order_only": "Orden impresa",
        }.get(str(mode or "").strip().lower(), "Documentacion de despacho impresa")
        message_id = models.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "message_post",
            [[int(order_id)]],
            {
                "body": body,
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_note",
            },
        )
        if dedupe_key:
            self._posted_print_notes[dedupe_key] = int(message_id) if message_id else None
            while len(self._posted_print_notes) > 2000:
                self._posted_print_notes.pop(next(iter(self._posted_print_notes)))
        return {
            "success": True,
            "posted": True,
            "duplicate": False,
            "order_id": int(order_id),
            "message_id": int(message_id) if message_id else None,
            "event_key": safe_event_key,
        }

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

    @staticmethod
    def _build_or_domain(filters: List[Any]) -> List[Any]:
        if not filters:
            return []
        if len(filters) == 1:
            return [filters[0]]
        return ["|"] * (len(filters) - 1) + filters

    @staticmethod
    def _many2one_parts(raw_value: Any) -> tuple[Optional[int], str]:
        if raw_value is None or raw_value is False:
            return None, ""
        if isinstance(raw_value, (list, tuple)):
            raw_id = raw_value[0] if raw_value else None
            raw_name = raw_value[1] if len(raw_value) >= 2 else ""
        else:
            raw_id = raw_value
            raw_name = ""
        try:
            value_id = int(raw_id) if raw_id not in (None, False, "") else None
        except (TypeError, ValueError):
            value_id = None
        return value_id, str(raw_name or "").strip()

    def list_products(
        self,
        search: str = "",
        limit: int = 200,
        offset: int = 0,
        active_only: bool = True,
        inventory_only: bool = True,
        include_stock: bool = True,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Obtiene productos/variantes desde Odoo para consumo de APIs locales."""
        try:
            limit_value = max(1, min(int(limit), 1000))
        except (TypeError, ValueError):
            limit_value = 200
        try:
            offset_value = max(0, int(offset))
        except (TypeError, ValueError):
            offset_value = 0

        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        available_fields = models.execute_kw(
            db,
            uid,
            password,
            "product.product",
            "fields_get",
            [[], ["string"]],
        ) or {}
        available = set(available_fields.keys())

        domain: List[Any] = []
        if active_only and "active" in available:
            domain.append(("active", "=", True))

        type_field = "detailed_type" if "detailed_type" in available else "type" if "type" in available else ""
        if inventory_only and type_field:
            domain.append((type_field, "in", ["product", "consu"]))

        search_value = str(search or "").strip()
        if search_value:
            search_filters = []
            for field_name in ("name", "display_name", "default_code", "barcode"):
                if field_name in available:
                    search_filters.append((field_name, "ilike", search_value))
            domain.extend(self._build_or_domain(search_filters))

        fields = ["id"]
        base_candidates = [
            "name",
            "display_name",
            "default_code",
            "barcode",
            "product_tmpl_id",
            "uom_id",
            "categ_id",
            "active",
            "detailed_type",
            "type",
            "lst_price",
            "list_price",
            "standard_price",
        ]
        stock_candidates = [
            "qty_available",
            "virtual_available",
            "incoming_qty",
            "outgoing_qty",
        ]
        for field_name in base_candidates + (stock_candidates if include_stock else []):
            if field_name in available and field_name not in fields:
                fields.append(field_name)

        order_fields = []
        if "default_code" in available:
            order_fields.append("default_code asc")
        if "name" in available:
            order_fields.append("name asc")
        order_fields.append("id asc")

        kwargs: Dict[str, Any] = {
            "fields": fields,
            "limit": limit_value,
            "offset": offset_value,
            "order": ", ".join(order_fields),
        }
        if not active_only:
            kwargs["context"] = {"active_test": False}

        total = models.execute_kw(
            db,
            uid,
            password,
            "product.product",
            "search_count",
            [domain],
        )
        products = models.execute_kw(
            db,
            uid,
            password,
            "product.product",
            "search_read",
            [domain],
            kwargs,
        ) or []

        items = []
        for product in products:
            tmpl_id, tmpl_name = self._many2one_parts(product.get("product_tmpl_id"))
            uom_id, uom_name = self._many2one_parts(product.get("uom_id"))
            category_id, category_name = self._many2one_parts(product.get("categ_id"))
            price_field = next((name for name in ("lst_price", "list_price", "standard_price") if name in product), "")
            product_type = product.get("detailed_type") if "detailed_type" in product else product.get("type", "")

            item: Dict[str, Any] = {
                "id": product.get("id"),
                "default_code": str(product.get("default_code") or ""),
                "barcode": str(product.get("barcode") or ""),
                "name": str(product.get("display_name") or product.get("name") or ""),
                "display_name": str(product.get("display_name") or ""),
                "list_price": product.get(price_field, "") if price_field else "",
                "price_field": price_field,
                "active": bool(product.get("active", True)),
                "type": str(product_type or ""),
                "product_tmpl_id": tmpl_id,
                "product_template": tmpl_name,
                "uom_id": uom_id,
                "uom": uom_name,
                "category_id": category_id,
                "category": category_name,
            }
            if include_stock:
                for field_name in stock_candidates:
                    if field_name in product:
                        item[field_name] = product.get(field_name)
            items.append(item)

        total_value = int(total or 0)
        return {
            "items": items,
            "total": total_value,
            "limit": limit_value,
            "offset": offset_value,
            "has_more": offset_value + len(items) < total_value,
            "filters": {
                "search": search_value,
                "active_only": bool(active_only),
                "inventory_only": bool(inventory_only),
                "include_stock": bool(include_stock),
            },
        }

    def get_replenishment_products(
        self,
        max_products: int = 5000,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Productos almacenables con stock actual, proyectado, entradas y salidas pendientes.

        Solo lectura. Detecta el campo de tipo segun la version de Odoo:
        `is_storable` (17.2+/18), `detailed_type` (15-17) o `type` (<=14).
        """
        try:
            max_value = max(1, min(int(max_products), 20000))
        except (TypeError, ValueError):
            max_value = 5000

        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        available = set(
            (
                models.execute_kw(
                    db, uid, password, "product.product", "fields_get", [[], ["string"]]
                )
                or {}
            ).keys()
        )

        domain: List[Any] = []
        if "active" in available:
            domain.append(("active", "=", True))
        if "is_storable" in available:
            domain.append(("is_storable", "=", True))
        elif "detailed_type" in available:
            domain.append(("detailed_type", "=", "product"))
        elif "type" in available:
            domain.append(("type", "=", "product"))

        fields = ["id"]
        for field_name in (
            "display_name",
            "name",
            "default_code",
            "barcode",
            "uom_id",
            "categ_id",
            "qty_available",
            "virtual_available",
            "incoming_qty",
            "outgoing_qty",
        ):
            if field_name in available:
                fields.append(field_name)

        items: List[Dict[str, Any]] = []
        page_size = 500
        offset = 0
        while len(items) < max_value:
            page = models.execute_kw(
                db,
                uid,
                password,
                "product.product",
                "search_read",
                [domain],
                {
                    "fields": fields,
                    "limit": min(page_size, max_value - len(items)),
                    "offset": offset,
                    "order": "default_code asc, id asc" if "default_code" in available else "id asc",
                },
            ) or []
            for product in page:
                uom_id, uom_name = self._many2one_parts(product.get("uom_id"))
                category_id, category_name = self._many2one_parts(product.get("categ_id"))
                items.append(
                    {
                        "id": product.get("id"),
                        "default_code": str(product.get("default_code") or ""),
                        "barcode": str(product.get("barcode") or ""),
                        "name": str(product.get("display_name") or product.get("name") or ""),
                        "uom": uom_name,
                        "category_id": category_id,
                        "category": category_name,
                        "qty_available": product.get("qty_available") or 0.0,
                        "virtual_available": product.get("virtual_available") or 0.0,
                        "incoming_qty": product.get("incoming_qty") or 0.0,
                        "outgoing_qty": product.get("outgoing_qty") or 0.0,
                    }
                )
            if len(page) < page_size:
                break
            offset += len(page)
        return items

    def get_reorder_rules(
        self,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[int, Dict[str, float]]]:
        """Minimos/maximos de las reglas de reabastecimiento, sumados por producto.

        Devuelve None si el usuario no puede leer `stock.warehouse.orderpoint`
        (el monitor usa entonces el minimo por defecto de su propia config).
        """
        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        try:
            rules = models.execute_kw(
                db,
                uid,
                password,
                "stock.warehouse.orderpoint",
                "search_read",
                [[("active", "=", True)]],
                {"fields": ["product_id", "product_min_qty", "product_max_qty"]},
            ) or []
        except xmlrpc.client.Fault as exc:
            logger.warning("No se pudieron leer reglas de reabastecimiento: %s", self.humanize_exception(exc))
            return None

        by_product: Dict[int, Dict[str, float]] = {}
        for rule in rules:
            product_id, _ = self._many2one_parts(rule.get("product_id"))
            if product_id is None:
                continue
            entry = by_product.setdefault(product_id, {"min_qty": 0.0, "max_qty": 0.0, "rules": 0})
            entry["min_qty"] += float(rule.get("product_min_qty") or 0.0)
            entry["max_qty"] += float(rule.get("product_max_qty") or 0.0)
            entry["rules"] += 1
        return by_product

    def get_customer_delivered_quantities(
        self,
        since_date: str,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[int, float]:
        """Cantidad neta entregada a clientes por producto desde `since_date` (YYYY-MM-DD).

        Suma movimientos `done` hacia ubicaciones de cliente y resta las devoluciones
        desde cliente. Se agrega en Python para no depender de `read_group`, cuya
        firma cambio entre versiones de Odoo.
        """
        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        available = set(
            (
                models.execute_kw(db, uid, password, "stock.move", "fields_get", [[], ["string"]])
                or {}
            ).keys()
        )
        qty_field = "product_qty" if "product_qty" in available else "product_uom_qty"
        since_value = f"{since_date} 00:00:00"

        totals: Dict[int, float] = {}
        # Solo movimientos que salen de / vuelven a stock propio: los dropship
        # (proveedor -> cliente) no consumen inventario.
        directions = (
            ("location_id.usage", "location_dest_id.usage", 1.0),
            ("location_dest_id.usage", "location_id.usage", -1.0),
        )
        for internal_side, customer_side, sign in directions:
            domain = [
                ("state", "=", "done"),
                ("date", ">=", since_value),
                (internal_side, "=", "internal"),
                (customer_side, "=", "customer"),
            ]
            offset = 0
            page_size = 2000
            while True:
                moves = models.execute_kw(
                    db,
                    uid,
                    password,
                    "stock.move",
                    "search_read",
                    [domain],
                    {"fields": ["product_id", qty_field], "limit": page_size, "offset": offset, "order": "id asc"},
                ) or []
                for move in moves:
                    product_id, _ = self._many2one_parts(move.get("product_id"))
                    if product_id is None:
                        continue
                    totals[product_id] = totals.get(product_id, 0.0) + sign * float(move.get(qty_field) or 0.0)
                if len(moves) < page_size:
                    break
                offset += len(moves)
        return totals

    def record_url(self, model: str, record_id: Any) -> str:
        """URL de formulario clasica; Odoo 17+ la redirige a su ruta nueva."""
        return f"{self._base_url()}/web#id={int(record_id)}&model={model}&view_type=form"

    def _readonly_session(self, auth_override: Optional[Dict[str, str]] = None):
        runtime = self._build_runtime_config(auth_override)
        uid = self._authenticate(auth_override=auth_override)
        models = self._xmlrpc_models(runtime)
        db = runtime.get("database", "")
        password = runtime.get("password", "")

        def call(model: str, method: str, args: List[Any], kwargs: Optional[Dict[str, Any]] = None) -> Any:
            return models.execute_kw(db, uid, password, model, method, args, kwargs or {})

        return uid, call

    @staticmethod
    def _search_read_all(call: Any, model: str, domain: List[Any], fields: List[str], order: str, page_size: int = 2000) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        offset = 0
        while True:
            page = call(model, "search_read", [domain], {"fields": fields, "limit": page_size, "offset": offset, "order": order}) or []
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += len(page)

    def get_receivables_data(
        self,
        payments_since: str,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Facturas y notas de credito de cliente abiertas, contactos y ultimo cobro. Solo lectura."""
        _, call = self._readonly_session(auth_override)
        moves = self._search_read_all(
            call,
            "account.move",
            [
                ("move_type", "in", ["out_invoice", "out_refund"]),
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
            ],
            [
                "name",
                "move_type",
                "partner_id",
                "commercial_partner_id",
                "invoice_date",
                "invoice_date_due",
                "amount_total",
                "amount_residual",
                "amount_residual_signed",
                "currency_id",
                "invoice_payment_term_id",
                "invoice_user_id",
                "payment_state",
            ],
            "invoice_date_due asc, id asc",
        )
        partner_ids = set()
        for move in moves:
            for key in ("commercial_partner_id", "partner_id"):
                partner_id, _ = self._many2one_parts(move.get(key))
                if partner_id:
                    partner_ids.add(partner_id)

        partners: Dict[int, Dict[str, Any]] = {}
        if partner_ids:
            for partner in call(
                "res.partner",
                "read",
                [sorted(partner_ids)],
                {"fields": ["name", "display_name", "vat", "email", "phone", "mobile"]},
            ) or []:
                partners[int(partner["id"])] = partner

        commercial_ids = sorted(
            {
                pid
                for pid in (self._many2one_parts(m.get("commercial_partner_id"))[0] for m in moves)
                if pid
            }
        )
        last_payments: Dict[int, Dict[str, Any]] = {}
        if commercial_ids:
            try:
                payments = self._search_read_all(
                    call,
                    "account.payment",
                    [
                        ("partner_type", "=", "customer"),
                        ("payment_type", "=", "inbound"),
                        ("state", "=", "posted"),
                        ("date", ">=", payments_since),
                        ("partner_id", "child_of", commercial_ids),
                    ],
                    ["partner_id", "date", "amount", "currency_id"],
                    "date desc, id desc",
                )
                # child_of trae pagos de contactos hijos: agrupar por entidad comercial.
                child_to_commercial: Dict[int, int] = {}
                payment_partner_ids = sorted(
                    {pid for pid in (self._many2one_parts(p.get("partner_id"))[0] for p in payments) if pid}
                )
                if payment_partner_ids:
                    for partner in call(
                        "res.partner", "read", [payment_partner_ids], {"fields": ["commercial_partner_id"]}
                    ) or []:
                        commercial_id, _ = self._many2one_parts(partner.get("commercial_partner_id"))
                        child_to_commercial[int(partner["id"])] = commercial_id or int(partner["id"])
                for payment in payments:
                    partner_id, _ = self._many2one_parts(payment.get("partner_id"))
                    commercial_id = child_to_commercial.get(partner_id or 0)
                    if commercial_id and commercial_id not in last_payments:
                        _, currency = self._many2one_parts(payment.get("currency_id"))
                        last_payments[commercial_id] = {
                            "date": payment.get("date"),
                            "amount": payment.get("amount"),
                            "currency": currency,
                        }
            except xmlrpc.client.Fault as exc:
                logger.warning("No se pudieron leer los cobros de clientes: %s", self.humanize_exception(exc))

        companies = call("res.company", "search_read", [[]], {"fields": ["name"], "limit": 1}) or []
        return {
            "moves": moves,
            "partners": partners,
            "last_payments": last_payments,
            "company_name": str(companies[0].get("name") or "") if companies else "",
        }

    def get_company_branding(
        self,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Logo (base64), colores de documentos y datos de contacto de la compania principal."""
        _, call = self._readonly_session(auth_override)
        available = set((call("res.company", "fields_get", [[], ["type"]]) or {}).keys())
        wanted = [
            name
            for name in (
                "name", "logo", "primary_color", "secondary_color", "street", "street2",
                "city", "phone", "email", "website", "vat",
            )
            if name in available
        ]
        companies = call("res.company", "search_read", [[]], {"fields": wanted, "limit": 1, "order": "id asc"}) or []
        return companies[0] if companies else {}

    def get_uninvoiced_sale_orders(
        self,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Ordenes de venta confirmadas con algo pendiente de facturar. Solo lectura.

        Cada orden incluye ``invoiced_total`` y ``refunded_total`` (facturas y
        notas de credito publicadas): Odoo vuelve a marcar "a facturar" una
        orden cuya factura se anulo con nota de credito.
        """
        _, call = self._readonly_session(auth_override)
        orders = self._search_read_all(
            call,
            "sale.order",
            [("state", "=", "sale"), ("invoice_status", "=", "to invoice")],
            [
                "name",
                "date_order",
                "partner_id",
                "amount_total",
                "amount_to_invoice",
                "currency_id",
                "team_id",
                "user_id",
                "client_order_ref",
                "invoice_ids",
            ],
            "date_order asc, id asc",
        )
        move_ids = sorted({int(move_id) for order in orders for move_id in (order.get("invoice_ids") or [])})
        moves: Dict[int, Dict[str, Any]] = {}
        if move_ids:
            for move in self._search_read_all(
                call,
                "account.move",
                [
                    ("id", "in", move_ids),
                    ("state", "=", "posted"),
                    ("move_type", "in", ["out_invoice", "out_refund"]),
                ],
                ["move_type", "amount_total"],
                "id asc",
            ):
                moves[int(move["id"])] = move
        for order in orders:
            linked = [moves[int(move_id)] for move_id in (order.get("invoice_ids") or []) if int(move_id) in moves]
            order["invoiced_total"] = round(
                sum(float(move.get("amount_total") or 0) for move in linked if move.get("move_type") == "out_invoice"), 2
            )
            order["refunded_total"] = round(
                sum(float(move.get("amount_total") or 0) for move in linked if move.get("move_type") == "out_refund"), 2
            )
        return orders

    def get_today_alerts(
        self,
        today: str,
        sample_size: int = 8,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Entregas y recepciones atrasadas y actividades vencidas, con una muestra de cada una."""
        uid, call = self._readonly_session(auth_override)
        pending_states = ["confirmed", "waiting", "assigned"]
        picking_fields = ["name", "partner_id", "scheduled_date", "origin", "state"]

        def block(model: str, domain: List[Any], fields: List[str], order: str) -> Dict[str, Any]:
            try:
                return {
                    "count": int(call(model, "search_count", [domain]) or 0),
                    "items": call(model, "search_read", [domain], {"fields": fields, "limit": sample_size, "order": order}) or [],
                }
            except xmlrpc.client.Fault as exc:
                return {"count": None, "items": [], "error": self.humanize_exception(exc)}

        late_deliveries = block(
            "stock.picking",
            [("picking_type_code", "=", "outgoing"), ("state", "in", pending_states), ("scheduled_date", "<", today)],
            picking_fields,
            # Primero lo recien atrasado: lo de hace meses suele ser arrastre a limpiar.
            "scheduled_date desc",
        )
        late_receipts = block(
            "stock.picking",
            [("picking_type_code", "=", "incoming"), ("state", "in", pending_states), ("scheduled_date", "<", today)],
            picking_fields,
            "scheduled_date desc",
        )
        activity_fields = ["summary", "res_name", "res_model", "res_id", "date_deadline", "user_id", "activity_type_id"]
        my_activities = block(
            "mail.activity",
            [("date_deadline", "<=", today), ("user_id", "=", uid)],
            activity_fields,
            "date_deadline asc",
        )
        all_activities = block("mail.activity", [("date_deadline", "<", today)], activity_fields, "date_deadline asc")

        for item in late_deliveries["items"] + late_receipts["items"]:
            item["url"] = self.record_url("stock.picking", item["id"])
        for item in my_activities["items"] + all_activities["items"]:
            if item.get("res_model") and item.get("res_id"):
                item["url"] = self.record_url(item["res_model"], item["res_id"])
        return {
            "late_deliveries": late_deliveries,
            "late_receipts": late_receipts,
            "my_activities": my_activities,
            "overdue_activities": all_activities,
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

    def attach_pdf_to_payment(
        self,
        payment_id: int,
        filename: str,
        pdf_bytes: bytes,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Adjunta un PDF al pago, sin duplicarlo por nombre."""
        if not payment_id or not pdf_bytes:
            raise ValueError("Faltan datos para adjuntar el comprobante al pago")
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

    def attach_totalnet_receipt_to_payment(
        self,
        payment_id: int,
        filename: str,
        pdf_bytes: bytes,
        auth_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Compatibilidad con el flujo POS existente."""
        return self.attach_pdf_to_payment(
            payment_id,
            filename,
            pdf_bytes,
            auth_override,
        )

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
        writeoff_label: str = "Redondeo cobro POS TotalNet",
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
                    "writeoff_label": writeoff_label,
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
        if isinstance(result, dict) and result.get("res_model") == "account.payment":
            if result.get("res_id"):
                payment_id = int(result["res_id"])
            elif result.get("res_ids"):
                payment_id = int(result["res_ids"][-1])
        if not payment_id:
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
