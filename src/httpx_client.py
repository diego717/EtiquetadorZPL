from __future__ import annotations

import threading
from typing import Optional

import httpx

_thread_local = threading.local()


def get_sync_http_client() -> httpx.Client:
    """Devuelve un cliente HTTPX persistente por hilo para aprovechar connection pooling."""
    client = getattr(_thread_local, "httpx_client", None)
    client_state = getattr(client, "_state", None) if client is not None else None
    if client is None or getattr(client_state, "name", "") != "UNOPENED":
        client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        _thread_local.httpx_client = client
    return client


def close_sync_http_client() -> None:
    client = getattr(_thread_local, "httpx_client", None)
    if client is not None:
        try:
            client.close()
        finally:
            _thread_local.httpx_client = None
