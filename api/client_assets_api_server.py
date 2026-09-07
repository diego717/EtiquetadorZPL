"""
Servidor minimo para busqueda local de CDR y previews.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _configure_runtime_paths() -> Path:
    if hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).resolve().parent.parent

    os.chdir(base_dir)

    for extra in (base_dir, base_dir / "api", base_dir / "src", base_dir / "config"):
        extra_str = str(extra)
        if extra_str not in sys.path:
            sys.path.insert(0, extra_str)

    return base_dir


BASE_DIR = _configure_runtime_paths()

from client_assets_endpoints import router as client_assets_router  # noqa: E402
from client_assets_service import client_assets_service  # noqa: E402


app = FastAPI(
    title="EtiquetadorZPL Client Assets API",
    description="API local para busqueda de archivos CDR y previews.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(client_assets_router)


@app.get("/")
async def root():
    return {
        "status": "running",
        "service": "client-assets-api",
        "config": client_assets_service.get_public_config(),
    }


@app.get("/api/status")
async def status():
    return {
        "status": "running",
        "framework": "FastAPI",
        "service": "client-assets-api",
        "config": client_assets_service.get_public_config(),
    }


def start_client_assets_api_server() -> None:
    host = os.environ.get("CLIENT_ASSETS_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("CLIENT_ASSETS_API_PORT", "8003"))

    print(f"Client Assets API ejecutandose en http://{host}:{port}")
    print(f"Documentacion: http://{host}:{port}/docs")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    start_client_assets_api_server()
