"""
Lectura de la hoja TRABAJOS de la planilla de produccion (solo lectura).

La planilla expone la hoja como JSON por una Web App de Apps Script
(googleScripts/16_TrabajosApi.txt) protegida con token. La URL y el token viven
en trabajos_api.json: primero en la carpeta de configuracion de la app y, si no
esta, en config/ del proyecto. No se usa la Sheets API porque la organizacion
bloquea la creacion de claves de service account.

Puede haber varias planillas (cada una con su Web App):

    {"sheets": [
        {"id": "principal", "name": "Produccion", "url": "...", "token": "..."},
        {"id": "otra", "name": "Otra planilla", "url": "...", "token": "...",
         "printers": {"label": "Godex GE300", "order": "EPSON L1250 Series"}}
    ]}

"printers" es opcional: sin eso se usan las impresoras de la configuracion de Odoo.
El formato de una sola planilla ({"url": ..., "token": ...}) sigue valiendo y se
llama "principal".
"""

from __future__ import annotations

import base64
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "trabajos_api.json"
DEFAULT_SHEET_ID = "principal"
# Varias pantallas abiertas (PC del taller + celulares) comparten una sola lectura.
CACHE_TTL_SECONDS = 60.0
REQUEST_TIMEOUT_SECONDS = 45
STATE_LOG_FILENAME = "trabajos_estado_historial.json"
STATE_LOG_MAX = 1000

# Columnas de la hoja (1 = A) que el Apps Script no informa en "columns".
# Salen de los encabezados de la fila 2.
COL_REQUESTED_BY = 1  # A "Pedido por"
COL_RECEIVED = 7  # G "Ingreso"
COL_DUE = 8  # H "Entrega"
COL_FINISHED = 10  # J "Finalizado"
COL_DAYS_LEFT = 12  # L "Entrega": dias hasta la entrega, negativo = atrasado
COL_PRIORITY = 14  # N "Prioridad"
COL_KIND = 21  # U: VENTA / FABRICACION (sin encabezado)

DEFAULT_COLUMNS = {
    "order": 2,
    "link": 3,
    "customer": 4,
    "product": 5,
    "quantity": 6,
    "state": 9,
    "newRowCheckbox": 11,
    "secondaryCheckbox": 13,
    "manufacturingId": 18,
}


def _config_candidates() -> List[Path]:
    paths: List[Path] = []
    try:
        from config_manager import config_manager

        paths.append(Path(config_manager.get_config_directory()) / CONFIG_FILENAME)
    except Exception:
        pass
    paths.append(Path(__file__).resolve().parent.parent / "config" / CONFIG_FILENAME)
    return paths


def _config_path() -> Path:
    for path in _config_candidates():
        if path.exists():
            return path
    raise RuntimeError(f"Falta {CONFIG_FILENAME}: configurar la Web App de la planilla")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")


def load_sheet_configs() -> List[Dict[str, Any]]:
    path = _config_path()
    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if isinstance(data.get("sheets"), list):
        entries = data["sheets"]
    else:
        entries = [{"id": DEFAULT_SHEET_ID, "name": data.get("name") or "Planilla principal", **data}]

    configs: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries):
        sheet_id = _slug(str(entry.get("id") or "")) or f"planilla-{index + 1}"
        url = str(entry.get("url") or "").strip()
        token = str(entry.get("token") or "").strip()
        if not url or not token:
            raise RuntimeError(f"{path}: la planilla '{sheet_id}' no tiene url y token")
        if any(c["id"] == sheet_id for c in configs):
            raise RuntimeError(f"{path}: hay dos planillas con el id '{sheet_id}'")
        printers = entry.get("printers") if isinstance(entry.get("printers"), dict) else {}
        configs.append({
            "id": sheet_id,
            "name": str(entry.get("name") or sheet_id).strip(),
            "url": url,
            "token": token,
            "printers": {
                "label": str(printers.get("label") or "").strip(),
                "order": str(printers.get("order") or "").strip(),
            },
        })
    if not configs:
        raise RuntimeError(f"{path}: no hay ninguna planilla configurada")
    return configs


def _cell(values: List[Any], column: int) -> str:
    index = column - 1
    if 0 <= index < len(values):
        return str(values[index] or "").strip()
    return ""


def _is_checked(text: str) -> bool:
    return text.upper() in ("TRUE", "VERDADERO")


def _parse_int(text: str) -> Optional[int]:
    try:
        return int(text.replace(".", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _manufacturing_url(record_id: str) -> str:
    if not record_id.isdigit():
        return ""
    try:
        from odoo_integration import odoo_integration

        return odoo_integration.record_url("mrp.production", record_id)
    except Exception:
        return ""


def parse_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    columns = {**DEFAULT_COLUMNS, **(payload.get("columns") or {})}
    items: List[Dict[str, Any]] = []
    for raw in payload.get("rows") or []:
        values = raw.get("values") or []
        kind = _cell(values, COL_KIND).lower()
        manufacturing_id = _cell(values, columns["manufacturingId"])
        link = str(raw.get("link") or "") or _manufacturing_url(manufacturing_id)
        items.append({
            "row": raw.get("row"),
            "order": _cell(values, columns["order"]),
            "kind": "fabricacion" if kind.startswith("fabric") else "venta" if kind == "venta" else "",
            "customer": _cell(values, columns["customer"]),
            "product": _cell(values, columns["product"]),
            "quantity": _cell(values, columns["quantity"]),
            "state": _cell(values, columns["state"]),
            "requested_by": _cell(values, COL_REQUESTED_BY),
            "received": _cell(values, COL_RECEIVED),
            "due": _cell(values, COL_DUE),
            # Fecha completa (AAAA-MM-DD) si la celda es fecha; "due" es el texto visible sin año.
            "due_date": str(raw.get("dueDate") or ""),
            "finished": _cell(values, COL_FINISHED),
            "days_left": _parse_int(_cell(values, COL_DAYS_LEFT)),
            "first": _is_checked(_cell(values, columns["newRowCheckbox"])),
            "supplier": _is_checked(_cell(values, columns["secondaryCheckbox"])),
            "priority": _cell(values, COL_PRIORITY),
            "link": link,
            "state_color": str(raw.get("stateColor") or ""),
        })
    return items


class TrabajosSheet:
    def __init__(self, sheet_id: str = "") -> None:
        self.sheet_id = sheet_id
        self._lock = threading.Lock()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_at = 0.0

    def _load_config(self) -> Dict[str, Any]:
        # Se relee en cada pedido: agregar una planilla no requiere reiniciar el servidor.
        configs = load_sheet_configs()
        if not self.sheet_id:
            return configs[0]
        for config in configs:
            if config["id"] == self.sheet_id:
                return config
        raise RuntimeError(f"No existe la planilla '{self.sheet_id}' en {CONFIG_FILENAME}")

    def printers(self) -> Dict[str, str]:
        return dict(self._load_config().get("printers") or {})

    def is_configured(self) -> bool:
        try:
            self._load_config()
            return True
        except Exception:
            return False

    def _request_get(self, **params: str) -> Dict[str, Any]:
        config = self._load_config()
        response = requests.get(
            config["url"], params={"token": config["token"], **params}, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            # Si la Web App no esta publicada para "Cualquiera", Google responde la pagina de login.
            raise RuntimeError("La planilla no devolvio datos: revisar que la Web App este publicada para 'Cualquiera'")
        if not payload.get("ok"):
            raise RuntimeError(f"La planilla respondio con error: {payload.get('error') or 'desconocido'}")
        return payload

    def list_preloaded(self) -> List[Dict[str, str]]:
        files = self._request_get(action="preloadedList").get("files")
        if files is None:
            raise RuntimeError("La Web App no tiene la version nueva publicada (falta preloadedList)")
        return [{"id": str(item.get("id") or ""), "name": str(item.get("nombre") or "")} for item in files]

    def get_preloaded_pdf(self, file_id: str) -> Dict[str, Any]:
        payload = self._request_get(action="preloadedFile", id=file_id)
        pdf_bytes = base64.b64decode(payload.get("pdfBase64") or "")
        if not pdf_bytes.startswith(b"%PDF"):
            raise RuntimeError("El archivo de Drive no es un PDF valido")
        return {"name": str(payload.get("name") or file_id), "pdf": pdf_bytes}

    def _fetch(self) -> Dict[str, Any]:
        payload = self._request_get()
        headers = payload.get("headers") or []
        return {
            "items": parse_rows(payload),
            "states": [str(state) for state in payload.get("states") or [] if str(state).strip()],
            "title": _cell(headers[0], 4) if headers else "",
            "generated_at": payload.get("generatedAt") or "",
            "sheet_elapsed_ms": payload.get("elapsedMs"),
        }

    def get(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            fresh = self._cache is not None and time.monotonic() - self._cache_at < CACHE_TTL_SECONDS
            if fresh and not force:
                return {**self._cache, "cached": True}
            try:
                self._cache = {**self._fetch(), "error": ""}
                self._cache_at = time.monotonic()
                return {**self._cache, "cached": False}
            except Exception as error:
                logger.warning("No se pudo leer la hoja TRABAJOS: %s", error)
                if self._cache is None:
                    raise
                # Mejor mostrar lo ultimo leido que una pantalla vacia; la pagina avisa del error.
                return {**self._cache, "cached": True, "error": str(error)}


    def set_state(self, row: int, order: str, product: str, state: str, user: str) -> Dict[str, Any]:
        config = self._load_config()
        body = {
            "token": config["token"],
            "action": "setState",
            "row": row,
            "order": order,
            "product": product,
            "state": state,
            "user": user,
        }
        # Apps Script ejecuta el POST y redirige a una URL que devuelve el resultado.
        response = requests.post(config["url"], json=body, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError("La planilla no devolvio respuesta: revisar que la Web App tenga la version nueva publicada")
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "La planilla rechazo el cambio")
        # La planilla se reordena despues del cambio: la proxima lectura tiene que ser fresca.
        with self._lock:
            self._cache = None
        _append_state_log({
            "at": datetime.now(timezone.utc).isoformat(),
            "sheet": self.sheet_id or DEFAULT_SHEET_ID,
            "user": user,
            "order": order,
            "product": product,
            "from": result.get("previousState", ""),
            "to": result.get("state", state),
            "changed": bool(result.get("changed")),
            "automation_error": result.get("automationError", ""),
        })
        return result

    def state_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        sheet_id = self.sheet_id or DEFAULT_SHEET_ID
        # Las entradas de antes de tener varias planillas no tienen "sheet": son de la principal.
        entries = [e for e in _read_state_log() if (e.get("sheet") or DEFAULT_SHEET_ID) == sheet_id]
        return list(reversed(entries[-limit:]))


def _state_log_path() -> Path:
    return _config_candidates()[0].with_name(STATE_LOG_FILENAME)


def _read_state_log() -> List[Dict[str, Any]]:
    path = _state_log_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


_state_log_lock = threading.Lock()


def _append_state_log(entry: Dict[str, Any]) -> None:
    # En la planilla todos los cambios figuran a nombre del dueno de la Web App;
    # aca queda quien lo hizo desde la app.
    with _state_log_lock:
        entries = _read_state_log()
        entries.append(entry)
        path = _state_log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(entries[-STATE_LOG_MAX:], handle, ensure_ascii=False, indent=1)
        except OSError as error:
            logger.warning("No se pudo guardar el historial de estados: %s", error)


class TrabajosSheets:
    """Una instancia (con su cache) por planilla configurada."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._instances: Dict[str, TrabajosSheet] = {}

    def list(self) -> List[Dict[str, str]]:
        return [{"id": c["id"], "name": c["name"]} for c in load_sheet_configs()]

    def get(self, sheet_id: str = "") -> TrabajosSheet:
        configs = load_sheet_configs()
        wanted = _slug(sheet_id) if sheet_id else configs[0]["id"]
        if not any(c["id"] == wanted for c in configs):
            raise KeyError(f"No existe la planilla '{sheet_id}'")
        with self._lock:
            if wanted not in self._instances:
                self._instances[wanted] = TrabajosSheet(wanted)
            return self._instances[wanted]

    def is_configured(self) -> bool:
        try:
            load_sheet_configs()
            return True
        except Exception:
            return False


trabajos_sheets = TrabajosSheets()
