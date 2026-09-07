"""
Endpoints locales para busqueda de CDR y previews por cliente.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from client_assets_service import client_assets_service

router = APIRouter(prefix="/api/client-assets", tags=["client-assets"])


class ClientAssetsConfigRequest(BaseModel):
    enabled: bool = False
    root_folder: str = ""
    use_alphabetical_buckets: bool = True
    search_strategy: str = "recursive_filename"
    preview_cache_dir: str = ""
    credito_keyword: str = "credito"
    corel_enabled: bool = True
    corel_visible: bool = False
    corel_open_visible: bool = True
    corel_bring_to_front: bool = True
    embedded_thumbnail_fallback: bool = True
    preview_width: int = 1200
    preview_height: int = 0
    preview_dpi: int = 120
    max_files_per_client: int = 100
    corel_macro: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "project_name": "",
            "module_name": "ClientAssetsPrepare",
            "entrypoint": "PrepareClientAsset",
            "profile_entrypoints": {
                "tarjetas_plasticas": "PrepareTarjetasPlasticas",
                "tarjetas_laminar_tinta_a": "PrepareTarjetasLaminarTintaA",
                "tarjetas_laminar_tinta_b": "PrepareTarjetasLaminarTintaB",
            },
            "fallback_to_python_prepare": True,
            "debug_enabled": True,
        }
    )
    corel_prepare_profiles: Dict[str, Dict[str, Any]] = Field(
        default_factory=lambda: {
            "tarjetas_plasticas": {
                "label": "Tarjetas plasticas",
                "printer_name": "",
                "paper_name": "",
                "orientation": "",
                "print_profile_name": "",
                "notes": "",
            },
            "tarjetas_laminar_tinta_a": {
                "label": "Tarjetas para laminar / tinta - Impresora A",
                "printer_name": "",
                "paper_name": "",
                "orientation": "",
                "print_profile_name": "",
                "notes": "",
            },
            "tarjetas_laminar_tinta_b": {
                "label": "Tarjetas para laminar / tinta - Impresora B",
                "printer_name": "",
                "paper_name": "",
                "orientation": "",
                "print_profile_name": "",
                "notes": "",
            },
        }
    )


class OpenInCorelRequest(BaseModel):
    item_id: str
    mode: Literal["open_only", "open_and_prepare"] = "open_only"
    profile_id: str | None = None


class PrewarmPreviewsRequest(BaseModel):
    item_ids: list[str]
    limit: int = 8
    force_refresh: bool = False


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return client_assets_service.get_public_config()


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return client_assets_service.get_public_config()


@router.post("/config")
async def save_config(config: ClientAssetsConfigRequest) -> Dict[str, Any]:
    try:
        return client_assets_service.save_config(config.dict())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/config/reload")
async def reload_config() -> Dict[str, Any]:
    try:
        return client_assets_service.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/search")
async def search_client_assets(
    client_name: str = Query(..., min_length=1),
    match_mode: Literal["strict", "broad"] = Query("strict"),
) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(client_assets_service.search_client_assets, client_name, match_mode)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/preview/{item_id}")
async def get_preview(item_id: str, force_refresh: bool = False) -> FileResponse:
    try:
        preview_path = await asyncio.to_thread(client_assets_service.get_preview_path, item_id, force_refresh)
        return FileResponse(preview_path, media_type="image/png")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/open-in-corel")
async def open_in_corel(request: OpenInCorelRequest) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(client_assets_service.open_in_corel, request.item_id, request.mode, request.profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/prewarm-previews")
async def prewarm_previews(request: PrewarmPreviewsRequest) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(
            client_assets_service.prewarm_previews,
            request.item_ids,
            request.limit,
            request.force_refresh,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
