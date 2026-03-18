"""
Integracion con Administrado para descargar etiquetas PDF.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import base64
import os
import sqlite3
import time
import html as html_lib
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import win32crypt
import win32con
import win32file
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)


class AdministradoIntegration:
    BASE_URL = "https://www.administrado.net"

    def __init__(self) -> None:
        self.config_path = self._resolve_config_path()
        self.storage_state_path = self.config_path.with_name("administrado_storage_state.json")
        self.config = self._load_config()
        self._playwright_runtime_lock = threading.Lock()
        self._playwright_runtime: Dict[str, Any] = {
            "driver": None,
            "browser": None,
            "context": None,
            "storage_mtime": None,
        }

    def _resolve_config_path(self) -> Path:
        try:
            from config_manager import config_manager

            return Path(config_manager.get_config_directory()) / "administrado_config.json"
        except Exception:
            import os

            base_dir = Path(os.environ.get("APPDATA", ".")) if os.name == "nt" else Path.home() / ".config"
            config_dir = base_dir / "EtiquetadorZPL"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / "administrado_config.json"

    def _default_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "base_url": self.BASE_URL,
            "sales_url": f"{self.BASE_URL}/seller/ventas3",
            "cookie_header": "",
            "default_printer": "",
            "default_copies": 1,
            "auto_crop_pdf": True,
            "use_playwright": True,
            "spooler_confirmation_timeout_seconds": 2.0,
            "spooler_poll_interval_seconds": 0.4,
            "last_error": "",
        }

    def _load_config(self) -> Dict[str, Any]:
        config = self._default_config()
        if self.config_path.exists():
            try:
                config.update(json.loads(self.config_path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning("No se pudo cargar configuracion de Administrado: %s", exc)
        return config

    def save_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update(updates)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self.config, indent=2, ensure_ascii=True), encoding="utf-8")
        return self.get_public_config()

    def get_public_config(self) -> Dict[str, Any]:
        safe = dict(self.config)
        if safe.get("cookie_header"):
            safe["cookie_header"] = "***"
        safe["configured"] = bool(self.config.get("cookie_header") or self.storage_state_path.exists())
        safe["config_path"] = str(self.config_path)
        safe["storage_state_path"] = str(self.storage_state_path)
        safe["playwright_session"] = self.storage_state_path.exists()
        return safe

    def _headers(self) -> Dict[str, str]:
        cookie_header = self.get_cookie_header()
        if not cookie_header:
            raise ValueError("Falta la cookie de sesion de Administrado")
        return {
            "Cookie": cookie_header,
            "User-Agent": "EtiquetadorZPL/1.0",
        }

    def request(self, path_or_url: str, *, timeout: int = 30) -> requests.Response:
        url = path_or_url if path_or_url.startswith("http") else f"{self.config.get('base_url', self.BASE_URL)}{path_or_url}"
        response = requests.get(url, headers=self._headers(), timeout=timeout, allow_redirects=True)
        return response

    def get_cookie_header(self) -> str:
        cookie_header = self.config.get("cookie_header", "").strip()
        if cookie_header:
            return cookie_header
        if self.storage_state_path.exists():
            return self._cookie_header_from_storage_state()
        return ""

    def import_browser_cookies(self, browser: str = "chrome", profile: str = "") -> Dict[str, Any]:
        browser_name = browser.lower().strip()
        browser_root = self._get_browser_root(browser_name)
        local_state_path = browser_root / "Local State"
        selected_profile = profile.strip() or self._guess_profile(browser_root)
        cookies_path = browser_root / selected_profile / "Network" / "Cookies"
        if not cookies_path.exists():
            cookies_path = browser_root / selected_profile / "Cookies"

        if not local_state_path.exists():
            raise ValueError(f"No se encontro Local State para {browser_name}")
        if not cookies_path.exists():
            raise ValueError(f"No se encontro la base de cookies para {browser_name} perfil {selected_profile}")

        master_key = self._get_browser_master_key(local_state_path)
        cookie_header = self._extract_cookie_header(cookies_path, master_key)
        self.save_config({
            "cookie_header": cookie_header,
            "last_error": "",
        })
        return {
            "browser": browser_name,
            "profile": selected_profile,
            "cookie_count": len(cookie_header.split("; ")) if cookie_header else 0,
            "configured": True,
        }

    def capture_playwright_session(self, timeout_seconds: int = 600) -> Dict[str, Any]:
        sync_playwright = self._get_playwright()
        login_url = self.config.get("sales_url", f"{self.BASE_URL}/seller/ventas3")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(login_url, wait_until="domcontentloaded")

            deadline = time.time() + timeout_seconds
            stable_hits = 0
            while time.time() < deadline:
                current_url = page.url
                cookies = context.cookies()
                admin_cookies = [item for item in cookies if "administrado.net" in item.get("domain", "")]
                has_session_cookie = any(
                    item.get("name", "").lower() in {"laravel_session", "remember_web", "xsrf-token"}
                    for item in admin_cookies
                )
                if (
                    "administrado.net" in current_url.lower()
                    and "login" not in current_url.lower()
                    and ("/seller/" in current_url.lower() or "/home" in current_url.lower())
                ):
                    stable_hits += 1
                else:
                    stable_hits = 0

                if stable_hits >= 3:
                    return self._persist_playwright_session(context, browser, current_url)
                if has_session_cookie and "login" not in current_url.lower():
                    return self._persist_playwright_session(context, browser, current_url)
                time.sleep(1)

            browser.close()
        raise TimeoutError("No se pudo capturar la sesion dentro del tiempo esperado. Inicia sesion completa y espera a entrar al panel interno de Administrado.")

    def list_label_links_playwright(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.storage_state_path.exists():
            raise ValueError("No hay sesion guardada de Playwright")

        sales_url = self.config.get("sales_url", f"{self.BASE_URL}/seller/ventas3")
        items: List[Dict[str, str]] = []

        with self._playwright_runtime_lock:
            for attempt in range(2):
                page = None
                try:
                    context = self._ensure_playwright_context_locked()
                    page = context.new_page()
                    page.goto(sales_url, wait_until="networkidle", timeout=120000)
                    items = page.evaluate(
                        """
                        () => {
                            const matches = [];
                            const elements = Array.from(document.querySelectorAll('a, button'));
                            for (const el of elements) {
                                const href = el.getAttribute('href') || '';
                                const text = (el.innerText || el.textContent || '').trim();
                                const qualifies = href.includes('/seller/envios/') || /imprimir etiqueta|reimprimir etiqueta/i.test(text);
                                if (!qualifies) continue;
                                const container = el.closest('tr, li, article, .row, .item, .card') || el.parentElement || el;
                                matches.push({
                                    href,
                                    text,
                                    context_text: (container.innerText || container.textContent || '').trim()
                                });
                            }
                            return matches;
                        }
                        """
                    )
                    break
                except Exception:
                    self._close_playwright_runtime_locked()
                    if attempt == 1:
                        raise
                finally:
                    if page is not None:
                        page.close()

        return self._extract_label_links_from_items(items, limit=limit)

    def test_session(self) -> Dict[str, Any]:
        if self.config.get("use_playwright", True) and self.storage_state_path.exists():
            try:
                return self._test_session_playwright()
            except Exception as exc:
                logger.warning("Fallo test de sesion con Playwright, usando requests: %s", exc)
        response = self.request(self.config.get("sales_url", f"{self.BASE_URL}/seller/ventas3"))
        ok = response.status_code == 200 and "login" not in response.url.lower()
        return {
            "ok": ok,
            "status_code": response.status_code,
            "final_url": response.url,
        }

    def list_label_links(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self.config.get("use_playwright", True) and self.storage_state_path.exists():
            try:
                return self.list_label_links_playwright(limit=limit)
            except Exception as exc:
                logger.warning("Fallo sincronizacion con Playwright, usando requests: %s", exc)

        response = self.request(self.config.get("sales_url", f"{self.BASE_URL}/seller/ventas3"), timeout=60)
        response.raise_for_status()
        html = response.text
        return self._extract_label_links_from_html(html, limit=limit)

    def _extract_label_links_from_html(self, html: str, limit: int = 20) -> List[Dict[str, Any]]:
        sales_from_payload = self._extract_sales_from_data_ventas(html, limit=limit)
        if sales_from_payload:
            return sales_from_payload

        pattern = re.compile(r"/seller/envios/(\d+)/(imprimir_etiqueta|reimprimir_etiqueta)")
        seen = set()
        sales: List[Dict[str, Any]] = []

        for match in pattern.finditer(html):
            envio_id = match.group(1)
            action = match.group(2)
            if envio_id in seen:
                continue
            seen.add(envio_id)
            context_text = self._extract_context_from_html(html, match.start(), match.end())
            customer_name, customer_username = self._extract_customer_fields(context_text)
            action = self._resolve_action(
                href=f"/seller/envios/{envio_id}/{action}",
                button_text="",
                context_text=context_text,
                fallback_action=action,
            )
            print_mode = self._action_to_mode(action)
            sales.append({
                "envio_id": envio_id,
                "action": action,
                "label_url": f"{self.config.get('base_url', self.BASE_URL)}/seller/envios/{envio_id}/{action}",
                "print_mode": print_mode,
                "is_reprint": print_mode == "reimprimir",
                "button_label": "Reimprimir etiqueta" if print_mode == "reimprimir" else "Imprimir etiqueta",
                "ready_to_print": True,
                "customer_name": customer_name,
                "customer_username": customer_username,
                "context_text": context_text,
            })
            if len(sales) >= limit:
                break

        return sales

    def _extract_sales_from_data_ventas(self, html: str, limit: int = 20) -> List[Dict[str, Any]]:
        match = re.search(r":data_ventas='(.*?)'", html, flags=re.DOTALL)
        if not match:
            return []

        raw_payload = html_lib.unescape(match.group(1))

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return []

        items = payload.get("data", []) if isinstance(payload, dict) else []
        sales: List[Dict[str, Any]] = []
        seen = set()

        for order in items:
            shipping_id = order.get("shipping_id")
            if not shipping_id:
                continue

            envio_id = str(shipping_id)
            if envio_id in seen:
                continue
            seen.add(envio_id)

            order_items = order.get("order_items_con_publicacion") or []
            first_item = order_items[0] if order_items else {}

            customer_name = (
                first_item.get("buyer_fullname")
                or order.get("billing_name")
                or ""
            )
            customer_username = first_item.get("buyer_nickname") or ""

            customer_name = self._normalize_buyer_name(customer_name)
            customer_username = customer_username.strip()

            is_reprint = str(order.get("label_printed", 0)) in {"1", "true", "True"}
            action = "reimprimir_etiqueta" if is_reprint else "imprimir_etiqueta"
            print_mode = self._action_to_mode(action)

            context_text = "\n".join(
                part for part in [
                    order.get("shipping_status", ""),
                    order.get("shipping_substatus", ""),
                    customer_name,
                    customer_username,
                    first_item.get("item_title", ""),
                ] if part
            ).strip()

            # Fallback final si fullname/nickname vinieron vacios
            if not customer_name or not customer_username:
                parsed_name, parsed_username = self._extract_customer_fields(context_text)
                customer_name = customer_name or parsed_name
                customer_username = customer_username or parsed_username

            sales.append({
                "envio_id": envio_id,
                "action": action,
                "label_url": f"{self.config.get('base_url', self.BASE_URL)}/seller/envios/{envio_id}/{action}",
                "print_mode": print_mode,
                "is_reprint": print_mode == "reimprimir",
                "button_label": "Reimprimir etiqueta" if print_mode == "reimprimir" else "Imprimir etiqueta",
                "ready_to_print": True,
                "customer_name": customer_name,
                "customer_username": customer_username,
                "context_text": context_text,
            })

            if len(sales) >= limit:
                break

        return sales

    def _normalize_buyer_name(self, value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""

        # "AntonellaEsteban" -> "Antonella Esteban"
        text = re.sub(r"([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])", r"\1 \2", text)
        text = re.sub(r"\s+", " ", text).strip()
        if self._looks_like_product_line(text):
            return ""
        return text

    def _extract_label_links_from_hrefs(self, hrefs: List[str], limit: int = 20) -> List[Dict[str, Any]]:
        pattern = re.compile(r"/seller/envios/(\d+)/(imprimir_etiqueta|reimprimir_etiqueta)")
        seen = set()
        sales: List[Dict[str, Any]] = []

        for href in hrefs:
            match = pattern.search(href or "")
            if not match:
                continue
            envio_id = match.group(1)
            action = self._resolve_action(href=href, fallback_action=match.group(2))
            if envio_id in seen:
                continue
            seen.add(envio_id)
            print_mode = self._action_to_mode(action)
            sales.append({
                "envio_id": envio_id,
                "action": action,
                "label_url": f"{self.config.get('base_url', self.BASE_URL)}/seller/envios/{envio_id}/{action}",
                "print_mode": print_mode,
                "is_reprint": print_mode == "reimprimir",
                "button_label": "Reimprimir etiqueta" if print_mode == "reimprimir" else "Imprimir etiqueta",
                "ready_to_print": True,
            })
            if len(sales) >= limit:
                break

        return sales

    def _extract_label_links_from_items(self, items: List[Dict[str, str]], limit: int = 20) -> List[Dict[str, Any]]:
        pattern = re.compile(r"/seller/envios/(\d+)/(imprimir_etiqueta|reimprimir_etiqueta)")
        seen = set()
        sales: List[Dict[str, Any]] = []

        for item in items:
            href = item.get("href", "") or ""
            context_text = item.get("context_text", "") or ""
            button_text = item.get("text", "") or ""
            full_context = "\n".join(part for part in [button_text, context_text] if part).strip()
            match = pattern.search(href) or pattern.search(full_context)
            if not match:
                continue

            envio_id = match.group(1)
            action = self._resolve_action(
                href=href,
                button_text=button_text,
                context_text=full_context,
                fallback_action=match.group(2),
            )
            if envio_id in seen:
                continue
            seen.add(envio_id)
            customer_name, customer_username = self._extract_customer_fields(full_context)
            print_mode = self._action_to_mode(action)

            sales.append({
                "envio_id": envio_id,
                "action": action,
                "label_url": f"{self.config.get('base_url', self.BASE_URL)}/seller/envios/{envio_id}/{action}",
                "print_mode": print_mode,
                "is_reprint": print_mode == "reimprimir",
                "button_label": "Reimprimir etiqueta" if print_mode == "reimprimir" else "Imprimir etiqueta",
                "ready_to_print": True,
                "customer_name": customer_name,
                "customer_username": customer_username,
                "context_text": full_context,
            })
            if len(sales) >= limit:
                break

        return sales

    def download_label_pdf(self, envio_id: str) -> bytes:
        response = self.request(f"/seller/envios/{envio_id}/imprimir_etiqueta", timeout=60)
        if response.status_code >= 400:
            response.raise_for_status()
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
            raise ValueError(f"La respuesta no parece ser un PDF valido. Content-Type: {content_type}")
        return response.content

    def process_downloaded_pdf(self, pdf_bytes: bytes, envio_id: str, printer: str = "") -> Dict[str, Any]:
        from handlers import PDFHandler
        from print_queue_monitor import get_print_jobs_from_spooler

        selected_printer = printer.strip() or self.get_default_printer()
        if not selected_printer:
            raise ValueError("No hay impresora configurada para Administrado")

        jobs_before = get_print_jobs_from_spooler(selected_printer, max_jobs=10)
        before_ids = {str(job.get("job_id")) for job in jobs_before if job.get("job_id") is not None}

        with tempfile.TemporaryDirectory(prefix="administrado_pdf_") as temp_dir:
            temp_path = Path(temp_dir)
            history_dir = temp_path / "historial"
            history_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = temp_path / f"administrado_{envio_id}.pdf"
            pdf_path.write_bytes(pdf_bytes)

            handler = PDFHandler(
                {
                    "entrada": str(temp_path),
                    "historial": str(history_dir),
                    "impresora": selected_printer,
                    "recortar_pdf": bool(self.config.get("auto_crop_pdf", True)),
                    "copias": int(self.config.get("default_copies", 1) or 1),
                    "poppler": "",
                },
                observer=None,
                root=None,
            )
            try:
                success = handler.procesar_pdf(str(pdf_path))
            finally:
                handler.shutdown()

        confirmation_timeout = self._as_float(
            self.config.get("spooler_confirmation_timeout_seconds", 2.0),
            default=2.0,
            min_value=0.0,
            max_value=10.0,
        )
        poll_interval = self._as_float(
            self.config.get("spooler_poll_interval_seconds", 0.4),
            default=0.4,
            min_value=0.1,
            max_value=2.0,
        )
        jobs_after, new_job_ids, waited_seconds, polls = self._wait_for_spooler_diff(
            printer_name=selected_printer,
            before_ids=before_ids,
            timeout_seconds=confirmation_timeout,
            poll_interval_seconds=poll_interval,
            max_jobs=10,
            get_jobs_fn=get_print_jobs_from_spooler,
        )

        return {
            "envio_id": envio_id,
            "printer": selected_printer,
            "success": bool(success),
            "verification": {
                "spooler_checked": True,
                "jobs_before": len(jobs_before),
                "jobs_after": len(jobs_after),
                "new_job_detected": bool(new_job_ids),
                "new_job_ids": new_job_ids,
                "waited_seconds": round(waited_seconds, 2),
                "polls": polls,
            },
        }

    def get_default_printer(self) -> str:
        printer = self.config.get("default_printer", "").strip()
        if printer:
            return printer

        try:
            from config_manager import config_manager

            app_config = config_manager.load_config()
            folders = app_config.get("carpetas", [])
            if folders:
                return folders[0].get("impresora", "").strip()
        except Exception:
            pass
        return ""

    def _cookie_header_from_storage_state(self) -> str:
        data = json.loads(self.storage_state_path.read_text(encoding="utf-8"))
        cookies = []
        for item in data.get("cookies", []):
            domain = item.get("domain", "")
            if "administrado.net" in domain:
                cookies.append(f"{item.get('name')}={item.get('value')}")
        return "; ".join(cookies)

    def _get_playwright(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ValueError(
                "Playwright no esta instalado. Ejecuta: pip install playwright && python -m playwright install chromium"
            ) from exc
        return sync_playwright

    def _persist_playwright_session(self, context, browser, current_url: str) -> Dict[str, Any]:
        context.storage_state(path=str(self.storage_state_path))
        browser.close()
        self.close_playwright_runtime()
        self.save_config({"last_error": "", "cookie_header": ""})
        return {
            "success": True,
            "url": current_url,
            "storage_state_path": str(self.storage_state_path),
        }

    def _test_session_playwright(self) -> Dict[str, Any]:
        sales_url = self.config.get("sales_url", f"{self.BASE_URL}/seller/ventas3")
        with self._playwright_runtime_lock:
            context = self._ensure_playwright_context_locked()
            page = context.new_page()
            try:
                page.goto(sales_url, wait_until="domcontentloaded", timeout=120000)
                time.sleep(2)
                current_url = page.url
            finally:
                page.close()

        return {
            "ok": "login" not in current_url.lower() and "administrado.net" in current_url.lower(),
            "status_code": 200,
            "final_url": current_url,
        }

    @staticmethod
    def _as_float(value: Any, default: float, min_value: float, max_value: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        if number < min_value:
            return min_value
        if number > max_value:
            return max_value
        return number

    def _wait_for_spooler_diff(
        self,
        *,
        printer_name: str,
        before_ids: set[str],
        timeout_seconds: float,
        poll_interval_seconds: float,
        max_jobs: int,
        get_jobs_fn,
    ) -> Tuple[List[Dict[str, Any]], List[str], float, int]:
        start = time.time()
        jobs_after: List[Dict[str, Any]] = []
        new_job_ids: List[str] = []
        polls = 0

        while True:
            polls += 1
            jobs_after = get_jobs_fn(printer_name, max_jobs=max_jobs)
            after_ids = {str(job.get("job_id")) for job in jobs_after if job.get("job_id") is not None}
            new_job_ids = sorted(after_ids - before_ids)
            elapsed = time.time() - start
            if new_job_ids or elapsed >= timeout_seconds:
                return jobs_after, new_job_ids, elapsed, polls
            time.sleep(poll_interval_seconds)

    def _storage_state_mtime(self) -> Optional[float]:
        try:
            return self.storage_state_path.stat().st_mtime
        except OSError:
            return None

    def _ensure_playwright_context_locked(self):
        if not self.storage_state_path.exists():
            raise ValueError("No hay sesion guardada de Playwright")

        runtime = self._playwright_runtime
        storage_mtime = self._storage_state_mtime()
        if runtime.get("context") is not None and runtime.get("storage_mtime") == storage_mtime:
            return runtime["context"]

        self._close_playwright_runtime_locked()
        sync_playwright = self._get_playwright()
        driver = sync_playwright().start()
        browser = driver.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(self.storage_state_path))
        runtime["driver"] = driver
        runtime["browser"] = browser
        runtime["context"] = context
        runtime["storage_mtime"] = storage_mtime
        return context

    def _close_playwright_runtime_locked(self) -> None:
        runtime = self._playwright_runtime
        context = runtime.get("context")
        browser = runtime.get("browser")
        driver = runtime.get("driver")

        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if driver is not None:
            try:
                driver.stop()
            except Exception:
                pass

        runtime["driver"] = None
        runtime["browser"] = None
        runtime["context"] = None
        runtime["storage_mtime"] = None

    def close_playwright_runtime(self) -> None:
        with self._playwright_runtime_lock:
            self._close_playwright_runtime_locked()

    def _extract_context_from_html(self, html: str, start_idx: int, end_idx: int, window: int = 700) -> str:
        left = max(0, start_idx - window)
        right = min(len(html), end_idx + window)
        snippet = html[left:right]
        snippet = html_lib.unescape(snippet)
        snippet = re.sub(r"<\s*br\s*/?\s*>", "\n", snippet, flags=re.IGNORECASE)
        snippet = re.sub(r"</\s*(div|li|tr|td|p|span|a|button|h[1-6])\s*>", "\n", snippet, flags=re.IGNORECASE)
        snippet = re.sub(r"<[^>]+>", " ", snippet)
        return snippet

    def _action_to_mode(self, action: str) -> str:
        return "reimprimir" if str(action).lower() == "reimprimir_etiqueta" else "imprimir"

    def _resolve_action(
        self,
        href: str,
        button_text: str = "",
        context_text: str = "",
        fallback_action: str = "imprimir_etiqueta",
    ) -> str:
        text = f"{button_text}\n{context_text}".lower()
        href_lower = (href or "").lower()

        if "reimprimir etiqueta" in text:
            return "reimprimir_etiqueta"
        if "imprimir etiqueta" in text:
            return "imprimir_etiqueta"
        if "/reimprimir_etiqueta" in href_lower:
            return "reimprimir_etiqueta"
        if "/imprimir_etiqueta" in href_lower:
            return "imprimir_etiqueta"
        return fallback_action or "imprimir_etiqueta"

    def _normalize_context_lines(self, context_text: str) -> List[str]:
        lines: List[str] = []
        seen = set()
        for raw_line in context_text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" \t-_|:;,.")
            if not line:
                continue
            if len(line) > 90:
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
        return lines

    def _looks_like_status_line(self, line: str) -> bool:
        return bool(
            re.search(
                r"(imprimir|etiqueta|reimprimir|envio a acordar|pendiente|despach|cancelad|"
                r"publicacion|operacion|ventas|factura|mensaje|comprador|cliente|producto|"
                r"precio|total|modificar|detalle|flex)",
                line,
                re.IGNORECASE,
            )
        )

    def _looks_like_product_line(self, line: str) -> bool:
        return bool(
            re.search(
                r"(articulo|producto|pack|combo|funda|cable|cargador|auricular|"
                r"telefono|celular|fono|repuesto|modelo|color|talle|medida|cm|mm|gb|tb|"
                r"iphone|samsung|xiaomi|motorola|huawei|vidrio|templado|camara|parlante|adaptador)",
                line,
                re.IGNORECASE,
            )
        )

    def _looks_like_date_or_number(self, line: str) -> bool:
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}(?:\s+\d{1,2}:\d{2})?", line):
            return True
        if re.fullmatch(r"[#]?\d+(?:[.,]\d+)?", line):
            return True
        if re.search(r"\$\s*\d", line):
            return True
        return False

    def _looks_like_username(self, line: str) -> bool:
        if " " in line:
            return False
        if len(line) < 3 or len(line) > 24:
            return False
        if self._looks_like_status_line(line) or self._looks_like_date_or_number(line):
            return False
        if self._looks_like_product_line(line):
            return False
        if not re.fullmatch(r"[A-Za-z0-9._-]+", line):
            return False
        if re.fullmatch(r"(FT|ML|ORD|SHIP)[A-Za-z0-9_-]*\d{8,}", line, re.IGNORECASE):
            return False
        if re.fullmatch(r"[A-Z]{2,}\d{10,}", line):
            return False
        return bool(re.search(r"[A-Za-z]", line))

    def _looks_like_person_name(self, line: str) -> bool:
        if self._looks_like_status_line(line) or self._looks_like_date_or_number(line):
            return False
        if self._looks_like_product_line(line):
            return False
        if re.search(r"\d", line):
            return False
        words = [word for word in re.split(r"\s+", line) if word]
        if len(words) < 2 or len(words) > 4:
            return False
        cleaned_words = [re.sub(r"[^A-Za-z\u00C0-\u017F'-]", "", word) for word in words]
        if any(len(word) < 2 for word in cleaned_words):
            return False
        if any(len(word) > 14 for word in cleaned_words):
            return False
        return True

    def _extract_labeled_value(self, lines: List[str], labels: List[str]) -> str:
        for idx, line in enumerate(lines):
            normalized = line.lower()
            for label in labels:
                label_norm = label.lower()
                if normalized.startswith(label_norm + ":") or normalized == label_norm:
                    value = line.split(":", 1)[1].strip() if ":" in line else ""
                    if value:
                        return value
                    if idx + 1 < len(lines):
                        return lines[idx + 1]
        return ""

    def _extract_customer_fields(self, context_text: str) -> Tuple[str, str]:
        lines = self._normalize_context_lines(context_text)
        if not lines:
            return "", ""

        labeled_name = self._extract_labeled_value(lines, ["comprador", "cliente", "nombre"])
        labeled_user = self._extract_labeled_value(lines, ["usuario", "nickname", "alias", "user"])
        if labeled_name and self._looks_like_person_name(labeled_name):
            if labeled_user and self._looks_like_username(labeled_user):
                return labeled_name, labeled_user
            return labeled_name, ""

        username_candidates = [line for line in lines if self._looks_like_username(line)]

        # Prefer the line right above username as the real customer name.
        for username in username_candidates:
            idx = lines.index(username)
            for candidate_idx in range(max(0, idx - 2), idx):
                name_candidate = lines[candidate_idx]
                if self._looks_like_person_name(name_candidate):
                    return name_candidate, username

        first_name = next((line for line in lines if self._looks_like_person_name(line)), "")
        first_username = username_candidates[0] if username_candidates else ""
        return first_name, first_username

    def _guess_customer_name(self, context_text: str) -> str:
        name, _ = self._extract_customer_fields(context_text)
        return name

    def _guess_customer_username(self, context_text: str) -> str:
        _, username = self._extract_customer_fields(context_text)
        return username

    def _get_browser_root(self, browser_name: str) -> Path:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        if browser_name == "chrome":
            return local_app_data / "Google" / "Chrome" / "User Data"
        if browser_name == "edge":
            return local_app_data / "Microsoft" / "Edge" / "User Data"
        raise ValueError("Browser no soportado. Usa chrome o edge")

    def _guess_profile(self, browser_root: Path) -> str:
        candidates = ["Default"] + [f"Profile {i}" for i in range(1, 10)]
        for candidate in candidates:
            if (browser_root / candidate).exists():
                return candidate
        raise ValueError("No se encontro un perfil de navegador compatible")

    def _get_browser_master_key(self, local_state_path: Path) -> bytes:
        local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
        encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key_b64)
        if encrypted_key.startswith(b"DPAPI"):
            encrypted_key = encrypted_key[5:]
        return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]

    def _extract_cookie_header(self, cookies_path: Path, master_key: bytes) -> str:
        rows = self._read_cookie_rows(cookies_path)
        if rows is None:
            with tempfile.TemporaryDirectory(prefix="adm_cookies_") as temp_dir:
                temp_db = Path(temp_dir) / "Cookies"
                self._copy_locked_file(cookies_path, temp_db)
                rows = self._read_cookie_rows(temp_db)

        if rows is None:
            raise ValueError("No se pudo leer la base de cookies del navegador")

        cookies: Dict[str, str] = {}
        for name, encrypted_value, value, host_key in rows:
            decrypted = value or self._decrypt_cookie_value(encrypted_value, master_key)
            if decrypted:
                cookies[name] = decrypted

        if not cookies:
            raise ValueError("No se encontraron cookies de administrado.net en el navegador seleccionado")

        return "; ".join(f"{name}={cookie_value}" for name, cookie_value in cookies.items())

    def _read_cookie_rows(self, db_path: Path):
        try:
            db_uri = f"{db_path.resolve().as_uri()}?mode=ro&immutable=1"
            conn = sqlite3.connect(db_uri, uri=True)
        except sqlite3.Error:
            try:
                conn = sqlite3.connect(str(db_path))
            except sqlite3.Error:
                return None

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, encrypted_value, value, host_key
                FROM cookies
                WHERE host_key LIKE ? OR host_key LIKE ?
                """,
                ("%administrado.net", "administrado.net"),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def _decrypt_cookie_value(self, encrypted_value: bytes, master_key: bytes) -> str:
        if not encrypted_value:
            return ""

        if encrypted_value.startswith(b"v10") or encrypted_value.startswith(b"v11"):
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:]
            plain = AESGCM(master_key).decrypt(nonce, ciphertext, None)
            return plain.decode("utf-8", errors="replace")

        try:
            return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _copy_locked_file(self, source: Path, target: Path) -> None:
        try:
            shutil.copy2(source, target)
            return
        except PermissionError:
            pass

        handle = win32file.CreateFile(
            str(source),
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        )

        try:
            with open(target, "wb") as temp_file:
                while True:
                    error_code, data = win32file.ReadFile(handle, 1024 * 1024)
                    if not data:
                        break
                    temp_file.write(data)
                    if len(data) < 1024 * 1024:
                        break
        finally:
            handle.Close()


administrado_integration = AdministradoIntegration()
