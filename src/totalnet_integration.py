"""
Integracion TotalNet (API REST, OAuth2 client_credentials) para conciliacion de pagos POS.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


TOTALNET_TRANSIENT_STATUS_CODES = {502, 503, 504}
TOTALNET_TRANSIENT_RETRY_DELAYS = (0.5, 1.5)


TOTALNET_TOKEN_URL = (
    "https://login.microsoftonline.com/6501733d-4f02-4ab5-8dbb-83b389f5ed49"
    "/oauth2/v2.0/token"
)
TOTALNET_API_BASE_URL = "https://apis.vnet.uy/adx-conecta"
TOTALNET_SCOPE = "https://vnetuy.onmicrosoft.com/auth/.default"
TOTALNET_SUBSCRIPTION_KEY = "7b75530503814d4ca395eb89ebf8b007"
OLD_TOTALNET_API_BASE_URL = "https://conecta.totalnet.uy/adx-conecta/v2"


class TotalNetIntegration:
    def __init__(self) -> None:
        self.config_path = self._resolve_config_path()
        self.config = self._load_config()
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @staticmethod
    def _resolve_config_path() -> Path:
        try:
            from config_manager import config_manager

            return Path(config_manager.get_config_directory()) / "totalnet_config.json"
        except Exception:
            import os

            if os.name == "nt":
                base_dir = Path(os.environ.get("APPDATA", "."))
            else:
                base_dir = Path.home() / ".config"
            config_dir = base_dir / "EtiquetadorZPL"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / "totalnet_config.json"

    def _default_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "client_id": "",
            "client_secret": "",
            "token_url": TOTALNET_TOKEN_URL,
            "api_base_url": TOTALNET_API_BASE_URL,
            "comercio": "",
            "sucursal": "",
            "last_error": "",
        }

    def _load_config(self) -> Dict[str, Any]:
        config = self._default_config()
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                config.update(saved)
                if config.get("api_base_url") == OLD_TOTALNET_API_BASE_URL:
                    config["api_base_url"] = TOTALNET_API_BASE_URL
                if not str(config.get("token_url") or "").strip():
                    config["token_url"] = TOTALNET_TOKEN_URL
            except Exception as exc:
                logger.warning("No se pudo cargar configuracion TotalNet: %s", exc)
        return config

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update(updates)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle, indent=2, ensure_ascii=True)
        # Cambio de credenciales invalida el token cacheado.
        self._token = None
        self._token_expires_at = 0.0
        return self.get_public_config()

    def get_public_config(self) -> Dict[str, Any]:
        safe = dict(self.config)
        if safe.get("client_secret"):
            safe["client_secret"] = "***"
        safe["configured"] = self.is_configured()
        safe["config_path"] = str(self.config_path)
        return safe

    def is_configured(self) -> bool:
        return bool(
            self.config.get("client_id")
            and self.config.get("client_secret")
            and self.config.get("token_url")
        )

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token

        token_url = str(self.config.get("token_url") or "").strip()
        client_id = str(self.config.get("client_id") or "").strip()
        client_secret = str(self.config.get("client_secret") or "").strip()

        if not token_url:
            raise ValueError(
                "Falta configurar la URL de token OAuth2 de TotalNet (campo 'token_url'). "
                "Buscarla en https://conecta.totalnet.uy/api-comercios-doc (seccion de seguridad/OAuth2)."
            )
        if not client_id or not client_secret:
            raise ValueError("Faltan client_id/client_secret de TotalNet")

        try:
            response = httpx.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": TOTALNET_SCOPE,
                },
                timeout=20,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"TotalNet rechazo la autenticacion OAuth2 ({exc.response.status_code}): {exc.response.text[:280]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"Error de red autenticando contra TotalNet: {exc}") from exc

        data = response.json()
        access_token = data.get("access_token")
        if not access_token:
            raise ValueError(f"Respuesta de token de TotalNet sin access_token: {data}")

        self._token = str(access_token)
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    def _post(
        self,
        path: str,
        payload: Dict[str, Any],
        *,
        allow_no_results: bool = False,
    ) -> Dict[str, Any]:
        token = self._get_token()
        base_url = str(self.config.get("api_base_url") or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("Falta api_base_url de TotalNet")

        attempts = len(TOTALNET_TRANSIENT_RETRY_DELAYS) + 1
        for attempt in range(attempts):
            try:
                response = httpx.post(
                    f"{base_url}{path}",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Ocp-Apim-Subscription-Key": TOTALNET_SUBSCRIPTION_KEY,
                    },
                    timeout=30,
                )

                if response.status_code == 404 and allow_no_results:
                    try:
                        error_data = response.json()
                        if isinstance(error_data, dict):
                            detail = (
                                error_data.get("detail")
                                or error_data.get("message")
                                or error_data.get("error")
                                or ""
                            )
                        else:
                            detail = error_data
                    except ValueError:
                        detail = response.text
                    if "no se encontraron" in str(detail).lower():
                        return {"_no_results": True, "detail": detail}

                if (
                    response.status_code in TOTALNET_TRANSIENT_STATUS_CODES
                    and attempt < attempts - 1
                ):
                    logger.warning(
                        "TotalNet devolvio %s en %s; reintento %s de %s",
                        response.status_code,
                        path,
                        attempt + 1,
                        attempts - 1,
                    )
                    time.sleep(TOTALNET_TRANSIENT_RETRY_DELAYS[attempt])
                    continue

                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                activity_id = ""
                try:
                    error_data = exc.response.json()
                    if isinstance(error_data, dict):
                        activity_id = str(error_data.get("activityId") or "").strip()
                except ValueError:
                    pass
                activity_text = f" ActivityId: {activity_id}." if activity_id else ""
                if exc.response.status_code == 500:
                    consequence = " y no se omitieron cupones" if path == "/cupones" else ""
                    raise ValueError(
                        "TotalNet tuvo un error interno (500) en "
                        f"{path}; es un fallo de su servicio{consequence}."
                        f"{activity_text}"
                    ) from exc
                raise ValueError(
                    f"TotalNet devolvio {exc.response.status_code} en {path}."
                    f"{activity_text} Respuesta: {exc.response.text[:280]}"
                ) from exc
            except httpx.HTTPError as exc:
                if attempt < attempts - 1:
                    logger.warning(
                        "Error de red llamando a TotalNet %s; reintento %s de %s: %s",
                        path,
                        attempt + 1,
                        attempts - 1,
                        exc,
                    )
                    time.sleep(TOTALNET_TRANSIENT_RETRY_DELAYS[attempt])
                    continue
                raise ValueError(f"Error de red llamando a TotalNet {path}: {exc}") from exc

        raise ValueError(f"No se pudo completar la consulta a TotalNet {path}")

    def test_connection(self) -> Dict[str, Any]:
        self._get_token()

        comercio = str(self.config.get("comercio") or "").strip()
        sucursal = str(self.config.get("sucursal") or "").strip()
        if not comercio or not sucursal:
            return {
                "ok": True,
                "token_ok": True,
                "api_checked": False,
                "message": "Token OAuth2 correcto. Complete comercio y sucursal para probar /cupones.",
                "token_url": self.config.get("token_url"),
                "api_base_url": self.config.get("api_base_url"),
            }

        try:
            comercio_num = int(comercio)
            sucursal_num = int(sucursal)
        except ValueError as exc:
            raise ValueError("Comercio y sucursal deben ser números enteros") from exc

        probe_date = (date.today() - timedelta(days=1)).isoformat()
        probe = self._post(
            "/cupones",
            {
                "comercio": comercio_num,
                "sucursal": sucursal_num,
                "fecha_liquidacion": probe_date,
                "page_number": 1,
            },
            allow_no_results=True,
        )
        return {
            "ok": True,
            "token_ok": True,
            "api_checked": True,
            "api_no_results": bool(probe.get("_no_results")),
            "probe_date": probe_date,
            "token_url": self.config.get("token_url"),
            "api_base_url": self.config.get("api_base_url"),
        }

    def get_cupones(
        self,
        fecha_liquidacion: str,
        page_number: int = 1,
        query_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"fecha_liquidacion": fecha_liquidacion}
        comercio = str(self.config.get("comercio") or "").strip()
        sucursal = str(self.config.get("sucursal") or "").strip()
        if not comercio or not sucursal:
            raise ValueError("TotalNet requiere configurar comercio y sucursal")
        try:
            payload["comercio"] = int(comercio)
            payload["sucursal"] = int(sucursal)
        except ValueError as exc:
            raise ValueError("Comercio y sucursal deben ser números enteros") from exc
        payload["page_number"] = page_number
        if query_name:
            payload["query_name"] = query_name
        return self._post("/cupones", payload, allow_no_results=True)

    def get_info(self) -> Dict[str, Any]:
        """Fechas con liquidaciones disponibles (POST /info).

        El schema de respuesta no esta confirmado contra la documentacion real
        de TotalNet (a diferencia de /cupones) -- se devuelve el JSON crudo tal
        cual lo entrega la API para poder inspeccionarlo antes de interpretarlo.
        """
        comercio = str(self.config.get("comercio") or "").strip()
        sucursal = str(self.config.get("sucursal") or "").strip()
        if not comercio or not sucursal:
            raise ValueError("TotalNet requiere configurar comercio y sucursal")
        try:
            payload = {"comercio": int(comercio), "sucursal": int(sucursal)}
        except ValueError as exc:
            raise ValueError("Comercio y sucursal deben ser números enteros") from exc
        return self._post("/info", payload, allow_no_results=True)

    def get_all_cupones(self, date_from: str, date_to: str, max_pages: int = 20) -> List[Dict[str, Any]]:
        """Recorre todas las paginas de /cupones para un rango de fechas."""
        try:
            first_date = date.fromisoformat(date_from)
            last_date = date.fromisoformat(date_to)
        except ValueError as exc:
            raise ValueError("Las fechas de TotalNet deben tener formato YYYY-MM-DD") from exc
        if last_date < first_date:
            raise ValueError("La fecha final no puede ser anterior a la fecha inicial")
        if last_date >= date.today():
            raise ValueError(
                "TotalNet no permite consultar la fecha actual ni fechas futuras; "
                "selecciona como fecha final ayer o un dia anterior"
            )

        all_items: List[Dict[str, Any]] = []
        current_date = first_date
        while current_date <= last_date:
            query_name: Optional[str] = None
            page_number = 1

            for _ in range(max_pages):
                queried_date = current_date.isoformat()
                try:
                    data = self.get_cupones(
                        queried_date,
                        page_number=page_number,
                        query_name=query_name,
                    )
                except ValueError as exc:
                    raise ValueError(
                        "No se pudo consultar TotalNet para la fecha de liquidacion "
                        f"{queried_date}, pagina {page_number}: {exc}"
                    ) from exc
                if data.get("_no_results"):
                    break
                all_items.extend(data.get("cupones") or [])

                total_pages = data.get("total_pages")
                query_name = data.get("query_name") or query_name
                if not total_pages or page_number >= int(total_pages):
                    break
                page_number += 1

            current_date += timedelta(days=1)

        return all_items


totalnet_integration = TotalNetIntegration()
