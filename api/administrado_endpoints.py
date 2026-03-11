"""
Endpoints para integracion con Administrado.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from administrado_integration import administrado_integration

router = APIRouter(prefix="/api/administrado", tags=["administrado"])


class AdministradoConfigRequest(BaseModel):
    enabled: bool = False
    base_url: str = "https://www.administrado.net"
    sales_url: str = "https://www.administrado.net/seller/ventas3"
    cookie_header: str = ""
    default_printer: str = ""
    default_copies: int = Field(default=1, ge=1, le=10)
    auto_crop_pdf: bool = True


class AdministradoPrintRequest(BaseModel):
    envio_id: str
    printer: str = ""


class AdministradoSyncRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)


class AdministradoCookieImportRequest(BaseModel):
    browser: str = "chrome"
    profile: str = ""


class AdministradoPlaywrightCaptureRequest(BaseModel):
    timeout_seconds: int = Field(default=600, ge=60, le=1200)


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return administrado_integration.get_public_config()


@router.post("/config")
async def save_config(config: AdministradoConfigRequest) -> Dict[str, Any]:
    payload = config.dict()
    if not payload.get("cookie_header"):
        payload.pop("cookie_header", None)
    return administrado_integration.save_config(payload)


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    return administrado_integration.get_public_config()


@router.post("/session/test")
async def test_session() -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(administrado_integration.test_session)
    except Exception as exc:
        administrado_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/cookies/import")
async def import_cookies(request: AdministradoCookieImportRequest) -> Dict[str, Any]:
    try:
        return administrado_integration.import_browser_cookies(
            browser=request.browser,
            profile=request.profile,
        )
    except Exception as exc:
        administrado_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/playwright/capture-session")
async def capture_playwright_session(request: AdministradoPlaywrightCaptureRequest) -> Dict[str, Any]:
    try:
        return await asyncio.to_thread(
            administrado_integration.capture_playwright_session,
            request.timeout_seconds,
        )
    except Exception as exc:
        administrado_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sales/sync")
async def sync_sales(request: AdministradoSyncRequest) -> Dict[str, Any]:
    try:
        sales = await asyncio.to_thread(
            administrado_integration.list_label_links,
            request.limit,
        )
        return {"sales": sales, "count": len(sales)}
    except Exception as exc:
        administrado_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/labels/print")
async def print_label(request: AdministradoPrintRequest) -> Dict[str, Any]:
    try:
        pdf_bytes = await asyncio.to_thread(
            administrado_integration.download_label_pdf,
            request.envio_id,
        )
        return await asyncio.to_thread(
            administrado_integration.process_downloaded_pdf,
            pdf_bytes,
            request.envio_id,
            request.printer,
        )
    except Exception as exc:
        administrado_integration.save_config({"last_error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc))
