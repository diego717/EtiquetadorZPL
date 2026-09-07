"""
Endpoints para integracion TotalNet (API de cupones/liquidaciones para conciliacion POS).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from totalnet_integration import totalnet_integration

router = APIRouter(prefix="/api/totalnet", tags=["totalnet"])


class TotalNetConfigRequest(BaseModel):
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    token_url: str = "https://login.microsoftonline.com/6501733d-4f02-4ab5-8dbb-83b389f5ed49/oauth2/v2.0/token"
    api_base_url: str = "https://apis.vnet.uy/adx-conecta"
    comercio: str = ""
    sucursal: str = ""


class TotalNetCuponesRequest(BaseModel):
    date_from: str
    date_to: str


def _friendly_error(exc: Exception) -> str:
    message = str(exc or "").strip()
    return message or "Error inesperado al comunicarse con TotalNet"


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return totalnet_integration.get_public_config()


@router.post("/config")
async def save_config(config: TotalNetConfigRequest) -> Dict[str, Any]:
    payload = config.dict()
    if not payload.get("client_secret"):
        payload.pop("client_secret", None)
    return totalnet_integration.save_config(payload)


@router.post("/session/test")
async def test_connection() -> Dict[str, Any]:
    try:
        result = await asyncio.to_thread(totalnet_integration.test_connection)
        totalnet_integration.save_config({"last_error": ""})
        return result
    except Exception as exc:
        message = _friendly_error(exc)
        totalnet_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/cupones")
async def get_cupones(request: TotalNetCuponesRequest) -> Dict[str, Any]:
    try:
        cupones = await asyncio.to_thread(
            totalnet_integration.get_all_cupones,
            request.date_from,
            request.date_to,
        )
        return {"date_from": request.date_from, "date_to": request.date_to, "items": cupones}
    except Exception as exc:
        message = _friendly_error(exc)
        totalnet_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)


@router.post("/info")
async def get_info() -> Dict[str, Any]:
    """Fechas con liquidaciones disponibles. Respuesta cruda: el schema de
    /info todavia no esta confirmado contra la documentacion real de TotalNet.
    """
    try:
        return await asyncio.to_thread(totalnet_integration.get_info)
    except Exception as exc:
        message = _friendly_error(exc)
        totalnet_integration.save_config({"last_error": message})
        raise HTTPException(status_code=400, detail=message)
