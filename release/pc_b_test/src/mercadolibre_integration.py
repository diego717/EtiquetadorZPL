"""
Integracion con Mercado Libre para descarga directa de etiquetas.
"""

from __future__ import annotations

import json
import logging
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)


class MercadoLibreIntegration:
    """Cliente simple para OAuth, notificaciones y etiquetas de Mercado Libre."""

    AUTH_URL = "https://auth.mercadolibre.com/authorization"
    API_BASE_URL = "https://api.mercadolibre.com"
    TOKEN_URL = f"{API_BASE_URL}/oauth/token"

    def __init__(self) -> None:
        self.config_path = self._resolve_config_path()
        self.config = self._load_config()

    def _resolve_config_path(self) -> Path:
        try:
            from config_manager import config_manager

            return Path(config_manager.get_config_directory()) / "mercadolibre_config.json"
        except Exception:
            import os

            if os.name == "nt":
                base_dir = Path(os.environ.get("APPDATA", "."))
            else:
                base_dir = Path.home() / ".config"
            config_dir = base_dir / "EtiquetadorZPL"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / "mercadolibre_config.json"

    def _default_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "client_id": "",
            "client_secret": "",
            "redirect_uri": "http://localhost:8002/api/mercadolibre/oauth/callback",
            "access_token": "",
            "refresh_token": "",
            "token_type": "Bearer",
            "expires_at": 0,
            "user_id": None,
            "nickname": "",
            "default_printer": "",
            "default_copies": 1,
            "auto_print": False,
            "response_type": "zpl2",
            "last_oauth_at": "",
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
                logger.warning("No se pudo cargar configuracion de Mercado Libre: %s", exc)
        return config

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update(updates)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle, indent=2, ensure_ascii=True)
        return self.get_public_config()

    def get_public_config(self) -> Dict[str, Any]:
        safe = dict(self.config)
        for key in ("client_secret", "access_token", "refresh_token"):
            if safe.get(key):
                safe[key] = "***"
        safe["configured"] = self.is_configured()
        safe["authenticated"] = bool(self.config.get("access_token"))
        safe["config_path"] = str(self.config_path)
        return safe

    def is_configured(self) -> bool:
        return bool(self.config.get("client_id") and self.config.get("client_secret"))

    def build_auth_url(self, state: Optional[str] = None) -> str:
        if not self.config.get("client_id"):
            raise ValueError("Falta client_id de Mercado Libre")

        params = {
            "response_type": "code",
            "client_id": self.config["client_id"],
            "redirect_uri": self.config.get("redirect_uri", ""),
        }
        if state:
            params["state"] = state
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> Dict[str, Any]:
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.config.get("client_id", ""),
            "client_secret": self.config.get("client_secret", ""),
            "code": code,
            "redirect_uri": self.config.get("redirect_uri", ""),
        }
        response = requests.post(self.TOKEN_URL, data=payload, timeout=30)
        response.raise_for_status()
        token_data = response.json()
        return self._store_token_data(token_data)

    def refresh_access_token(self) -> Dict[str, Any]:
        refresh_token = self.config.get("refresh_token")
        if not refresh_token:
            raise ValueError("No hay refresh_token configurado")

        payload = {
            "grant_type": "refresh_token",
            "client_id": self.config.get("client_id", ""),
            "client_secret": self.config.get("client_secret", ""),
            "refresh_token": refresh_token,
        }
        response = requests.post(self.TOKEN_URL, data=payload, timeout=30)
        response.raise_for_status()
        token_data = response.json()
        return self._store_token_data(token_data)

    def _store_token_data(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        expires_in = int(token_data.get("expires_in", 0) or 0)
        updates = {
            "access_token": token_data.get("access_token", ""),
            "refresh_token": token_data.get("refresh_token", self.config.get("refresh_token", "")),
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_at": int(time.time()) + max(expires_in - 60, 0),
            "user_id": token_data.get("user_id"),
            "last_oauth_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_error": "",
        }
        self.save_config(updates)
        try:
            me = self.get_me()
            self.save_config({
                "user_id": me.get("id", self.config.get("user_id")),
                "nickname": me.get("nickname", ""),
            })
        except Exception as exc:
            logger.warning("No se pudo obtener perfil de Mercado Libre: %s", exc)
        return self.get_public_config()

    def ensure_token(self) -> str:
        access_token = self.config.get("access_token", "")
        if not access_token:
            raise ValueError("No hay access_token configurado")

        expires_at = int(self.config.get("expires_at", 0) or 0)
        if expires_at and time.time() >= expires_at:
            logger.info("Access token vencido, refrescando token de Mercado Libre")
            self.refresh_access_token()
            access_token = self.config.get("access_token", "")

        return access_token

    def request(
        self,
        method: str,
        resource: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        retry_on_401: bool = True,
    ) -> requests.Response:
        access_token = self.ensure_token()
        request_headers = {
            "Authorization": f"Bearer {access_token}",
            "x-format-new": "true",
        }
        if headers:
            request_headers.update(headers)

        url = resource if resource.startswith("http") else f"{self.API_BASE_URL}{resource}"
        response = requests.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            headers=request_headers,
            timeout=timeout,
        )

        if response.status_code == 401 and retry_on_401 and self.config.get("refresh_token"):
            logger.info("Mercado Libre respondio 401, intentando refresh token")
            self.refresh_access_token()
            return self.request(
                method,
                resource,
                params=params,
                json_body=json_body,
                headers=headers,
                timeout=timeout,
                retry_on_401=False,
            )

        return response

    def get_order(self, order_id: str) -> Dict[str, Any]:
        response = self.request("GET", f"/orders/{order_id}")
        response.raise_for_status()
        return response.json()

    def get_me(self) -> Dict[str, Any]:
        response = self.request("GET", "/users/me")
        response.raise_for_status()
        return response.json()

    def get_shipment(self, shipment_id: str) -> Dict[str, Any]:
        response = self.request("GET", f"/shipments/{shipment_id}")
        response.raise_for_status()
        return response.json()

    def search_orders(self, limit: int = 20, offset: int = 0, status: str = "paid") -> Dict[str, Any]:
        seller_id = self.config.get("user_id")
        if not seller_id:
            me = self.get_me()
            seller_id = me.get("id")
            if seller_id:
                self.save_config({
                    "user_id": seller_id,
                    "nickname": me.get("nickname", self.config.get("nickname", "")),
                })

        if not seller_id:
            raise ValueError("No se pudo determinar el seller_id de Mercado Libre")

        response = self.request(
            "GET",
            "/orders/search",
            params={
                "seller": seller_id,
                "order.status": status,
                "sort": "date_desc",
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return response.json()

    def download_shipment_label(self, shipment_ids: List[str], response_type: Optional[str] = None) -> bytes:
        if not shipment_ids:
            raise ValueError("Se requiere al menos un shipment_id")

        selected_response_type = response_type or self.config.get("response_type", "zpl2")
        response = self.request(
            "GET",
            "/shipment_labels",
            params={
                "shipment_ids": ",".join(str(item) for item in shipment_ids),
                "response_type": selected_response_type,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.content

    def extract_zpl_from_label_payload(self, payload: bytes, response_type: Optional[str] = None) -> str:
        selected_response_type = response_type or self.config.get("response_type", "zpl2")
        if selected_response_type != "zpl2":
            raise ValueError("Solo se soporta extraccion automatica para response_type=zpl2")

        with zipfile.ZipFile(BytesIO(payload)) as archive:
            for member in archive.namelist():
                lower = member.lower()
                if lower.endswith(".txt") or lower.endswith(".zpl"):
                    with archive.open(member) as handle:
                        return handle.read().decode("utf-8", errors="replace")
        raise ValueError("No se encontro un archivo ZPL dentro del ZIP")

    def get_default_printer(self) -> str:
        printer = self.config.get("default_printer", "").strip()
        if printer:
            return printer

        try:
            from config_manager import config_manager

            app_config = config_manager.load_config()
            folders = app_config.get("carpetas", [])
            if folders:
                return folders[0].get("impresora", "").strip()
        except Exception:
            pass

        return ""

    def get_default_copies(self) -> int:
        copies = int(self.config.get("default_copies", 1) or 1)
        return max(copies, 1)

    def shipment_ready_to_print(self, shipment: Dict[str, Any]) -> bool:
        status = shipment.get("status")
        substatus = shipment.get("substatus")
        return status == "ready_to_ship" and substatus in (None, "", "printed", "ready_to_print")

    def resolve_shipment_id_from_notification(self, payload: Dict[str, Any]) -> Optional[str]:
        resource = str(payload.get("resource", "") or "")
        topic = str(payload.get("topic", "") or "")

        if topic.startswith("orders") and resource.startswith("/orders/"):
            order_id = resource.rstrip("/").split("/")[-1]
            order_data = self.get_order(order_id)
            shipping = order_data.get("shipping") or {}
            shipping_id = shipping.get("id")
            return str(shipping_id) if shipping_id else None

        if resource.startswith("/shipments/"):
            return resource.rstrip("/").split("/")[-1]

        return None

    def list_ready_to_print_sales(self, limit: int = 20) -> List[Dict[str, Any]]:
        orders_data = self.search_orders(limit=limit, offset=0, status="paid")
        results = orders_data.get("results", [])
        ready_sales: List[Dict[str, Any]] = []

        for order in results:
            shipping = order.get("shipping") or {}
            shipment_id = shipping.get("id")
            if not shipment_id:
                continue

            try:
                shipment = self.get_shipment(str(shipment_id))
            except Exception as exc:
                ready_sales.append({
                    "order_id": order.get("id"),
                    "shipment_id": str(shipment_id),
                    "order_status": order.get("status"),
                    "shipment_status": "error",
                    "shipment_substatus": "",
                    "buyer": (order.get("buyer") or {}).get("nickname") or (order.get("buyer") or {}).get("id"),
                    "title": self._extract_order_title(order),
                    "ready_to_print": False,
                    "error": str(exc),
                })
                continue

            ready = self.shipment_ready_to_print(shipment)
            ready_sales.append({
                "order_id": order.get("id"),
                "shipment_id": str(shipment_id),
                "order_status": order.get("status"),
                "shipment_status": shipment.get("status"),
                "shipment_substatus": shipment.get("substatus"),
                "buyer": (order.get("buyer") or {}).get("nickname") or (order.get("buyer") or {}).get("id"),
                "title": self._extract_order_title(order),
                "ready_to_print": ready,
                "error": "",
            })

        ready_sales.sort(key=lambda item: (not item.get("ready_to_print", False), str(item.get("order_id", ""))))
        return ready_sales

    def _extract_order_title(self, order: Dict[str, Any]) -> str:
        order_items = order.get("order_items") or []
        if not order_items:
            return ""
        item = order_items[0].get("item") or {}
        return str(item.get("title", ""))


mercadolibre_integration = MercadoLibreIntegration()
