"""Cache persistente de respuestas de Mercado Libre que no cambian.

Mercado Libre limita las consultas por minuto (HTTP 429). Una vez pagada la
venta, las ordenes de un pack y el costo de envio que pago el comprador quedan
fijos, asi que se guardan en disco para no volver a pedirlos en cada busqueda.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 30 * 24 * 3600
DEFAULT_MAX_ENTRIES = 3000


class PersistentCache:
    def __init__(
        self,
        path_resolver: Callable[[], Path],
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._path_resolver = path_resolver
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Optional[Dict[str, Dict[str, Any]]] = None

    @property
    def path(self) -> Path:
        return self._path_resolver()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self._entries is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._entries = data if isinstance(data, dict) else {}
            except FileNotFoundError:
                self._entries = {}
            except (OSError, ValueError) as exc:
                logger.warning("Cache de Mercado Libre ilegible, se descarta: %s", exc)
                self._entries = {}
        return self._entries

    def _save(self) -> None:
        entries = self._load()
        if len(entries) > self.max_entries:
            newest = sorted(entries.items(), key=lambda item: item[1].get("at", 0), reverse=True)
            self._entries = entries = dict(newest[: self.max_entries])
        try:
            path = self.path
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(entries, ensure_ascii=True), encoding="utf-8")
            temp_path.replace(path)
        except OSError as exc:
            # Sin cache solo se pierde eficiencia: nunca debe cortar la consulta.
            logger.warning("No se pudo guardar el cache de Mercado Libre: %s", exc)

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._load().get(key)
            if not entry or time.time() - float(entry.get("at", 0)) > self.ttl_seconds:
                return None
            return entry.get("value")

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._load()[key] = {"at": time.time(), "value": value}
            self._save()
