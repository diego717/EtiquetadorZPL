"""
Monitor de Cola de Impresión de Windows
Permite obtener trabajos de impresión del sistema, incluyendo impresoras de red
"""

import logging
import subprocess
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def get_print_jobs_from_spooler(printer_name: Optional[str] = None, max_jobs: int = 50) -> List[Dict[str, Any]]:
    """Obtiene los trabajos de impresión del spooler de Windows."""
    jobs = []
    
    try:
        if printer_name:
            ps_command = f"Get-PrintJob -PrinterName '{printer_name}' -ErrorAction SilentlyContinue | Select-Object JobId, DocumentName, PrinterName, SubmittedTime, Status, Owner, Pages, Size | ConvertTo-Json -Compress"
        else:
            ps_command = "Get-PrintJob -ErrorAction SilentlyContinue | Select-Object JobId, DocumentName, PrinterName, SubmittedTime, Status, Owner, Pages, Size | ConvertTo-Json -Compress"
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_command],
            capture_output=True,
            text=True,
            startupinfo=startupinfo
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip())
                if isinstance(data, dict):
                    data = [data]
                
                for job in data:
                    jobs.append({
                        'job_id': job.get('JobId'),
                        'document_name': job.get('DocumentName', 'Unknown'),
                        'printer_name': job.get('PrinterName', 'Unknown'),
                        'submitted_time': job.get('SubmittedTime'),
                        'status': job.get('Status', 'Unknown'),
                        'owner': job.get('Owner', 'Unknown'),
                        'pages': job.get('Pages', 0),
                        'size': job.get('Size', 0),
                        'source': 'spooler'
                    })
            except json.JSONDecodeError as e:
                logger.warning(f"Error al parsear JSON de trabajos: {e}")
                
    except Exception as e:
        logger.warning(f"Error al obtener trabajos del spooler: {e}")
    
    return jobs[-max_jobs:]


def get_all_printers_with_jobs() -> List[Dict[str, Any]]:
    """Obtiene todas las impresoras que tienen trabajos en cola."""
    printers_with_jobs = []
    
    try:
        ps_command = "Get-PrintJob | Select-Object -Property PrinterName -Unique | Select-Object -ExpandProperty PrinterName"
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_command],
            capture_output=True,
            text=True,
            startupinfo=startupinfo
        )
        
        if result.returncode == 0:
            printer_names = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            
            for printer in printer_names:
                jobs = get_print_jobs_from_spooler(printer)
                if jobs:
                    printers_with_jobs.append({
                        'printer_name': printer,
                        'job_count': len(jobs),
                        'jobs': jobs
                    })
                    
    except Exception as e:
        logger.warning(f"Error al obtener impresoras con trabajos: {e}")
    
    return printers_with_jobs


def get_network_printers() -> List[str]:
    """Obtiene la lista de impresoras de red disponibles."""
    network_printers = []
    
    try:
        ps_command = "Get-Printer | Select-Object Name, PortName | ConvertTo-Json -Compress"
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_command],
            capture_output=True,
            text=True,
            startupinfo=startupinfo
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip())
                if isinstance(data, dict):
                    data = [data]
                
                for printer in data:
                    name = printer.get('Name', '')
                    port = printer.get('PortName', '')
                    
                    # Detectar solo impresoras de red genuinas
                    is_network = False
                    
                    # WSD: Web Services on Devices (impresoras de red)
                    if 'WSD-' in port:
                        is_network = True
                    
                    # Puertos IP con formato IP_direccion o TCP
                    elif port.startswith('IP_') or port.startswith('TCP'):
                        is_network = True
                    
                    # Puertos con formato:serie (como EP9CE7BA:WF-C5790 SERIES) - impresoras Epson de red
                    elif ':' in port and not 'USB' in port and not 'COM' in port and not 'LPT' in port and 'PORTPROMPT' not in port:
                        # Verificar que no sea un puerto especial del sistema
                        if 'FILE:' not in port and 'PORTPROMPT' not in port:
                            is_network = True
                    
                    if is_network:
                        network_printers.append(name)
                        
            except json.JSONDecodeError:
                pass
        
        logger.info(f"Impresoras de red: {len(network_printers)}: {network_printers}")
            
    except Exception as e:
        logger.warning(f"Error al obtener impresoras de red: {e}")
    
    return network_printers


def get_all_printers() -> List[str]:
    """Obtiene todas las impresoras disponibles."""
    all_printers = []
    
    try:
        ps_command = "Get-Printer | Select-Object -ExpandProperty Name"
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_command],
            capture_output=True,
            text=True,
            startupinfo=startupinfo
        )
        
        if result.returncode == 0:
            all_printers = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        
        logger.info(f"Total impresoras: {len(all_printers)}")
            
    except Exception as e:
        logger.warning(f"Error al obtener impresoras: {e}")
    
    return all_printers


def get_recent_print_jobs_from_network(max_jobs: int = 20) -> List[Dict[str, Any]]:
    """Obtiene los trabajos recientes de impresoras de red."""
    all_jobs = []
    
    network_printers = get_network_printers()
    
    for printer in network_printers:
        jobs = get_print_jobs_from_spooler(printer, max_jobs)
        all_jobs.extend(jobs)
    
    all_jobs.sort(key=lambda x: x.get('submitted_time', ''), reverse=True)
    
    return all_jobs[:max_jobs * len(network_printers) if network_printers else max_jobs]


def cancel_print_job(printer_name: str, job_id: int) -> bool:
    """Cancela un trabajo de impresión."""
    try:
        ps_command = f"Remove-PrintJob -PrinterName '{printer_name}' -JobId {job_id} -ErrorAction Stop"
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_command],
            capture_output=True,
            text=True,
            startupinfo=startupinfo
        )
        
        if result.returncode == 0:
            logger.info(f"Trabajo {job_id} cancelado en {printer_name}")
            return True
        else:
            logger.warning(f"Error al cancelar trabajo: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error al cancelar trabajo: {e}")
        return False


def get_printer_status(printer_name: str) -> Optional[Dict[str, Any]]:
    """Obtiene el estado de una impresora."""
    try:
        ps_command = f"Get-Printer -Name '{printer_name}' -ErrorAction SilentlyContinue | Select-Object Name, PrinterStatus, PrinterState, Jobs, TotalJobs, TotalPagesPrinted | ConvertTo-Json -Compress"
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        
        result = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_command],
            capture_output=True,
            text=True,
            startupinfo=startupinfo
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip())
                return {
                    'name': data.get('Name'),
                    'status': data.get('PrinterStatus'),
                    'state': data.get('PrinterState'),
                    'jobs': data.get('Jobs', 0),
                    'total_jobs': data.get('TotalJobs', 0),
                    'total_pages': data.get('TotalPagesPrinted', 0)
                }
            except json.JSONDecodeError:
                pass
                
    except Exception as e:
        logger.warning(f"Error al obtener estado de impresora: {e}")
    
    return None


class PrintQueueMonitor:
    """Monitor de cola de impresión"""
    
    def __init__(self):
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 10
    
    def get_recent_jobs(self, include_spooler: bool = True, max_jobs: int = 20) -> List[Dict[str, Any]]:
        import time
        current_time = time.time()
        
        cache_key = f"spooler_{include_spooler}"
        
        if cache_key in self.cache:
            if current_time - self.cache_time.get(cache_key, 0) < self.cache_ttl:
                return self.cache[cache_key]
        
        jobs = []
        
        if include_spooler:
            spooler_jobs = get_recent_print_jobs_from_network(max_jobs)
            jobs.extend(spooler_jobs)
        
        jobs.sort(key=lambda x: x.get('submitted_time', ''), reverse=True)
        
        self.cache[cache_key] = jobs[:max_jobs]
        self.cache_time[cache_key] = current_time
        
        return self.cache[cache_key]
    
    def refresh_cache(self):
        self.cache.clear()
        self.cache_time.clear()


print_queue_monitor = PrintQueueMonitor()


def get_print_queue_monitor() -> PrintQueueMonitor:
    return print_queue_monitor

