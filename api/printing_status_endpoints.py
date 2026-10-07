"""
Estado de impresion para el panel de Impresion (web/index.html).

Muestra solo las impresoras que usa el flujo (orden, etiqueta y sus respaldos),
con el estado que informa Windows y un chequeo real de red: Windows suele decir
"lista" aunque la impresora este apagada.
"""

from __future__ import annotations

import asyncio
import re
import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/printing", tags=["printing"])

STALE_JOB_MINUTES = 30
NETWORK_PORTS = (9100, 631, 515)  # RAW, IPP, LPR

# Flags de PRINTER_INFO_2.Status (winspool.h) que interesan al operador.
STATUS_FLAGS = [
    (0x00000080, "Desconectada"),
    (0x00000002, "Error"),
    (0x00000008, "Papel atascado"),
    (0x00000010, "Sin papel"),
    (0x00040000, "Sin tinta / toner"),
    (0x00000020, "Requiere intervencion manual"),
    (0x00400000, "Puerta abierta"),
    (0x00000001, "En pausa"),
    (0x00100000, "Requiere atencion"),
]
PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x00000400


def _configured_printers() -> List[Dict[str, str]]:
    roles: List[Dict[str, str]] = []
    try:
        from odoo_integration import odoo_integration

        cfg = odoo_integration.config
        for key, role in (
            ("default_order_printer", "Orden Odoo"),
            ("fallback_order_printer", "Orden Odoo (respaldo)"),
            ("default_label_printer", "Etiqueta"),
            ("fallback_label_printer", "Etiqueta (respaldo)"),
        ):
            name = str(cfg.get(key) or "").strip()
            if name:
                roles.append({"name": name, "role": role})
    except Exception:
        pass
    try:
        from mercadolibre_integration import mercadolibre_integration

        name = str(mercadolibre_integration.config.get("default_printer") or "").strip()
        if name:
            roles.append({"name": name, "role": "Etiqueta Mercado Libre"})
    except Exception:
        pass

    merged: Dict[str, Dict[str, Any]] = {}
    for item in roles:
        entry = merged.setdefault(item["name"].lower(), {"name": item["name"], "roles": []})
        if item["role"] not in entry["roles"]:
            entry["roles"].append(item["role"])
    return list(merged.values())


def _host_from_port(port_name: str) -> str:
    """Puertos TCP/IP estandar se llaman como la IP, a veces con sufijo (192.168.1.5_3)."""
    match = re.match(r"^(?:IP_)?(\d{1,3}(?:\.\d{1,3}){3})", str(port_name or ""))
    return match.group(1) if match else ""


def _network_reachable(host: str, timeout: float = 1.0) -> Optional[bool]:
    if not host:
        return None
    for port in NETWORK_PORTS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def _printer_status(name: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {"name": name, "installed": False, "problems": [], "jobs": None, "port": "", "host": ""}
    try:
        import win32print  # type: ignore

        handle = win32print.OpenPrinter(name)
        try:
            data = win32print.GetPrinter(handle, 2)
        finally:
            win32print.ClosePrinter(handle)
    except Exception as exc:
        info["error"] = "No esta instalada en esta PC" if "1801" in str(exc) else str(exc)
        return info

    status = int(data.get("Status") or 0)
    attributes = int(data.get("Attributes") or 0)
    problems = [label for flag, label in STATUS_FLAGS if status & flag]
    if attributes & PRINTER_ATTRIBUTE_WORK_OFFLINE and "Desconectada" not in problems:
        problems.insert(0, "Desconectada")
    port = str(data.get("pPortName") or "")
    info.update(
        {
            "installed": True,
            "problems": problems,
            "jobs": int(data.get("cJobs") or 0),
            "port": port,
            "host": _host_from_port(port),
        }
    )
    return info


def _stale_jobs() -> List[Dict[str, Any]]:
    from database import db

    # created_at es CURRENT_TIMESTAMP de SQLite: UTC sin zona.
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_JOB_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    stale = []
    for status in ("pending", "processing"):
        for job in db.get_recent_jobs(500, status=status):
            if str(job.get("created_at") or "") < cutoff:
                stale.append({k: job.get(k) for k in ("id", "filename", "printer", "status", "created_at")})
    return sorted(stale, key=lambda job: job["id"])


@router.get("/printers")
async def key_printers() -> Dict[str, Any]:
    printers = _configured_printers()
    statuses = await asyncio.gather(*(asyncio.to_thread(_printer_status, p["name"]) for p in printers))
    reachability = await asyncio.gather(*(asyncio.to_thread(_network_reachable, s.get("host", "")) for s in statuses))
    items = []
    for printer, status, reachable in zip(printers, statuses, reachability):
        status["roles"] = printer["roles"]
        status["network_reachable"] = reachable
        if not status["installed"]:
            status["state"] = "error"
        elif status["problems"] or reachable is False:
            status["state"] = "error"
        elif status["jobs"]:
            status["state"] = "busy"
        else:
            status["state"] = "ok"
        items.append(status)
    return {"checked_at": datetime.now().astimezone().isoformat(), "items": items}


@router.get("/printers/{name}/queue")
async def printer_queue(name: str) -> Dict[str, Any]:
    from print_queue_monitor import get_print_jobs_from_spooler

    jobs = await asyncio.to_thread(get_print_jobs_from_spooler, name, 20)
    return {"name": name, "jobs": jobs}


@router.get("/stale-jobs")
async def stale_jobs() -> Dict[str, Any]:
    try:
        jobs = await asyncio.to_thread(_stale_jobs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Base de datos no disponible: {exc}")
    return {"minutes": STALE_JOB_MINUTES, "items": jobs}


@router.post("/stale-jobs/close")
async def close_stale_jobs() -> Dict[str, Any]:
    """Marca como fallidos los trabajos locales que quedaron colgados. No toca impresoras ni Odoo."""
    from database import db

    jobs = await asyncio.to_thread(_stale_jobs)
    closed = 0
    for job in jobs:
        if await asyncio.to_thread(
            db.update_job_status, job["id"], "failed", f"Cerrado manualmente: sin respuesta por mas de {STALE_JOB_MINUTES} minutos"
        ):
            closed += 1
    return {"closed": closed}
