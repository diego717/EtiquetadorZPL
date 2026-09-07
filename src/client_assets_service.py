"""
Servicios locales para buscar archivos de clientes y generar previews de CDR.
"""

from __future__ import annotations

import base64
import concurrent.futures
import math
import hashlib
import json
import logging
import os
import re
import threading
import unicodedata
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from get_writable_path import get_readable_config_path, get_writable_config_path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "root_folder": "C:/Trabajos",
    "use_alphabetical_buckets": True,
    "search_strategy": "recursive_filename",
    "preview_cache_dir": "",
    "credito_keyword": "credito",
    "corel_enabled": True,
    "corel_visible": False,
    "corel_open_visible": True,
    "corel_bring_to_front": True,
    "embedded_thumbnail_fallback": True,
    "preview_width": 1200,
    "preview_height": 0,
    "preview_dpi": 120,
    "max_files_per_client": 100,
    "corel_macro": {
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
    },
    "corel_prepare_profiles": {
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
    },
}


@dataclass
class ClientAssetItem:
    item_id: str
    name: str
    relative_path: str
    absolute_path: str
    contains_credito: bool
    match_reason: str
    modified_at: float
    preview_url: str


class ClientAssetsService:
    def __init__(self) -> None:
        self.config_path = Path(get_writable_config_path("client_assets_config.json"))
        self.config = self._load_config()
        self._preview_executor: Optional[concurrent.futures.ThreadPoolExecutor] = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="corel-preview",
        )
        self._preview_pythoncom = None
        self._preview_constants = None
        self._preview_app = None
        self._preview_thread_id: Optional[int] = None

    def _load_config(self) -> Dict[str, Any]:
        readable = get_readable_config_path("client_assets_config.json")
        if readable:
            try:
                with open(readable, "r", encoding="utf-8") as fh:
                    stored = json.load(fh)
                return self._merge_config_dicts(DEFAULT_CONFIG, stored)
            except Exception as exc:
                logger.warning("No se pudo leer client_assets_config.json: %s", exc)
        return dict(DEFAULT_CONFIG)

    def reload(self) -> Dict[str, Any]:
        self.config = self._load_config()
        return self.get_public_config()

    def save_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        new_config = self._merge_config_dicts(self.config, payload)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump(new_config, fh, indent=2, ensure_ascii=False)
        self.config = new_config
        return self.get_public_config()

    def _merge_config_dicts(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in (override or {}).items():
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                merged[key] = self._merge_config_dicts(existing, value)
            else:
                merged[key] = value
        return merged

    def _reset_preview_corel_session_before_interactive_open(self) -> None:
        executor = self._preview_executor
        if executor is None:
            return

        try:
            executor.submit(self._dispose_preview_corel_session).result(timeout=15)
        except Exception as exc:
            logger.warning(
                "No se pudo reiniciar la sesion de preview CorelDRAW antes de apertura interactiva: %s",
                exc,
            )

    def shutdown(self) -> None:
        executor = self._preview_executor
        if executor is None:
            return

        try:
            executor.submit(self._dispose_preview_corel_session).result(timeout=15)
        except Exception as exc:
            logger.warning("No se pudo cerrar la sesion persistente de preview CorelDRAW: %s", exc)
        finally:
            executor.shutdown(wait=True, cancel_futures=False)
            self._preview_executor = None

    def get_public_config(self) -> Dict[str, Any]:
        config = dict(self.config)
        root_folder = self._root_folder()
        preview_cache_dir = self._preview_cache_dir()
        config["root_folder_exists"] = bool(root_folder and root_folder.exists())
        config["preview_cache_dir_resolved"] = str(preview_cache_dir) if preview_cache_dir else ""
        return config

    def search_client_assets(self, client_name: str, match_mode: str = "strict") -> Dict[str, Any]:
        safe_client = str(client_name or "").strip()
        if not safe_client:
            raise ValueError("client_name vacio")

        safe_match_mode = str(match_mode or "strict").strip().lower()
        if safe_match_mode not in {"strict", "broad"}:
            raise ValueError("match_mode invalido. Usa 'strict' o 'broad'.")

        root_folder = self._root_folder()
        if not root_folder:
            raise ValueError("No hay carpeta raiz configurada para activos locales.")
        if not root_folder.exists():
            raise ValueError(f"La carpeta raiz no existe: {root_folder}")

        items = self._search_cdr_files_recursively(root_folder, safe_client, safe_match_mode)
        warnings: List[str] = []
        if not items:
            keyword = str(self.config.get("credito_keyword", "credito") or "credito")
            warnings.append(f'No se encontraron archivos .cdr con "{keyword}" para "{safe_client}".')

        matched_directories = self._collect_matched_directories(root_folder, items)
        folder_path = ""
        if len(matched_directories) == 1:
            folder_path = matched_directories[0]
        elif matched_directories:
            folder_path = str(root_folder)

        return {
            "client_name": safe_client,
            "folder_path": folder_path,
            "matched_directories": matched_directories,
            "match_count": len(items),
            "match_mode": safe_match_mode,
            "search_mode": str(self.config.get("search_strategy", "recursive_filename") or "recursive_filename"),
            "items": [item.__dict__ for item in items],
            "warnings": warnings,
        }

    def resolve_item_path(self, item_id: str) -> Path:
        decoded = self._decode_item_id(item_id)
        root_folder = self._root_folder()
        if not root_folder:
            raise ValueError("No hay carpeta raiz configurada.")

        candidate = (root_folder / decoded).resolve()
        root_resolved = root_folder.resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError("Ruta fuera de la carpeta raiz configurada.") from exc

        if not candidate.exists():
            raise FileNotFoundError(f"No existe el archivo solicitado: {candidate}")
        return candidate

    def get_preview_path(self, item_id: str, force_refresh: bool = False) -> Path:
        source_path = self.resolve_item_path(item_id)
        cache_path = self._build_cache_path(source_path)

        if cache_path.exists() and not force_refresh:
            return cache_path

        errors: List[str] = []

        if self.config.get("corel_enabled", True):
            try:
                self._export_cdr_preview_with_corel(source_path, cache_path)
            except Exception as exc:
                logger.warning(
                    "Fallo la generacion de preview via CorelDRAW para item_id=%s source=%s",
                    item_id,
                    source_path,
                    exc_info=True,
                )
                errors.append(self._format_preview_stage_error("corel_preview", exc))
        else:
            errors.append("corel_preview: La generacion de preview desde CorelDRAW esta deshabilitada.")

        if cache_path.exists():
            return cache_path

        if self.config.get("embedded_thumbnail_fallback", True):
            try:
                self._extract_embedded_thumbnail(source_path, cache_path)
            except Exception as exc:
                logger.warning(
                    "Fallo la miniatura embebida para item_id=%s source=%s",
                    item_id,
                    source_path,
                    exc_info=True,
                )
                errors.append(self._format_preview_stage_error("embedded_thumbnail", exc))

        if not cache_path.exists():
            message = " | ".join(error for error in errors if error)
            logger.error(
                "No se pudo generar preview para item_id=%s source=%s detalle=%s",
                item_id,
                source_path,
                message or "sin detalle",
            )
            raise RuntimeError(message or "No se pudo generar la preview del archivo CDR.")
        return cache_path

    def open_in_corel(self, item_id: str, mode: str = "open_only", profile_id: Optional[str] = None) -> Dict[str, Any]:
        if mode not in {"open_only", "open_and_prepare"}:
            raise ValueError(f"Modo no soportado por ahora: {mode}")

        source_path = self.resolve_item_path(item_id)
        if source_path.suffix.lower() != ".cdr":
            raise ValueError("El archivo seleccionado no es un .cdr.")

        selected_profile_id = str(profile_id or "").strip()
        selected_profile = None
        if mode == "open_and_prepare":
            if not selected_profile_id:
                raise ValueError("profile_id es obligatorio cuando mode=open_and_prepare.")
            selected_profile = self._resolve_corel_prepare_profile(selected_profile_id)

        self._reset_preview_corel_session_before_interactive_open()

        pythoncom, win32_client = self._load_corel_open_automation()
        warnings: List[str] = []
        applied_settings: Dict[str, Any] = {}
        macro_result: Dict[str, Any] = {}
        app = None
        doc = None

        pythoncom.CoInitialize()
        try:
            app = win32_client.gencache.EnsureDispatch("CorelDRAW.Application")
            app.Visible = bool(self.config.get("corel_open_visible", True))
            doc = app.OpenDocument(str(source_path))

            try:
                doc.Activate()
            except Exception:
                pass

            if bool(self.config.get("corel_open_visible", True)):
                try:
                    app.Visible = True
                except Exception:
                    pass

            if mode == "open_and_prepare" and selected_profile is not None:
                macro_result, macro_warnings = self._prepare_corel_document(
                    app,
                    doc,
                    selected_profile_id,
                    selected_profile,
                    source_path,
                )
                warnings.extend(macro_warnings)
                if not macro_result.get("used", False):
                    applied_settings, prepare_warnings = self._apply_corel_prepare_profile(
                        app,
                        doc,
                        selected_profile_id,
                        selected_profile,
                    )
                    warnings.extend(prepare_warnings)

            if bool(self.config.get("corel_bring_to_front", True)):
                warning = self._bring_corel_to_front(source_path)
                if warning:
                    warnings.append(warning)
        except Exception as exc:
            try:
                if doc is not None:
                    doc.Close()
            except Exception:
                pass
            raise RuntimeError(f"No se pudo abrir el archivo en CorelDRAW: {exc}") from exc
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

        root_folder = self._root_folder()
        relative_path = str(source_path)
        if root_folder:
            try:
                relative_path = str(source_path.resolve().relative_to(root_folder.resolve()))
            except ValueError:
                relative_path = str(source_path)

        return {
            "ok": True,
            "mode": mode,
            "profile_id": selected_profile_id or None,
            "item_id": item_id,
            "file_name": source_path.name,
            "relative_path": relative_path,
            "message": "Archivo abierto y preparado en CorelDRAW." if mode == "open_and_prepare" else "Archivo abierto en CorelDRAW.",
            "warnings": warnings,
            "applied_settings": applied_settings,
            "macro_result": macro_result,
        }

    def prewarm_previews(self, item_ids: List[str], limit: int = 8, force_refresh: bool = False) -> Dict[str, Any]:
        sanitized_item_ids = [str(item_id or "").strip() for item_id in (item_ids or []) if str(item_id or "").strip()]
        if not sanitized_item_ids:
            raise ValueError("item_ids vacio")

        normalized_limit = max(1, min(int(limit or 8), 50))
        unique_item_ids = list(dict.fromkeys(sanitized_item_ids))[:normalized_limit]

        results: List[Dict[str, Any]] = []
        warmed_count = 0
        cached_count = 0
        failed_count = 0

        for item_id in unique_item_ids:
            try:
                source_path = self.resolve_item_path(item_id)
                cache_path = self._build_cache_path(source_path)
                status = "cached" if cache_path.exists() and not force_refresh else "warmed"
                preview_path = self.get_preview_path(item_id, force_refresh=force_refresh)
                if status == "cached":
                    cached_count += 1
                else:
                    warmed_count += 1
                results.append(
                    {
                        "item_id": item_id,
                        "status": status,
                        "preview_path": str(preview_path),
                    }
                )
            except Exception as exc:
                failed_count += 1
                results.append(
                    {
                        "item_id": item_id,
                        "status": "failed",
                        "detail": str(exc),
                    }
                )

        return {
            "ok": True,
            "requested_count": len(sanitized_item_ids),
            "processed_count": len(unique_item_ids),
            "warmed_count": warmed_count,
            "cached_count": cached_count,
            "failed_count": failed_count,
            "items": results,
        }

    def _root_folder(self) -> Optional[Path]:
        raw = str(self.config.get("root_folder", "") or "").strip()
        return Path(raw) if raw else None

    def _preview_cache_dir(self) -> Path:
        raw = str(self.config.get("preview_cache_dir", "") or "").strip()
        if raw:
            cache_dir = Path(raw)
        else:
            base = Path(os.environ.get("APPDATA", ".")) / "EtiquetadorZPL"
            cache_dir = base / "client_assets_previews"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _search_cdr_files_recursively(self, root_folder: Path, client_name: str, match_mode: str = "strict") -> List[ClientAssetItem]:
        max_files = int(self.config.get("max_files_per_client", 100) or 100)
        keyword = self._normalize_text(self.config.get("credito_keyword", "credito"))
        credito_flag_keyword = self._normalize_text("credito")
        search_terms = self._build_search_terms(client_name, match_mode=match_mode)
        root_resolved = root_folder.resolve()

        scored_items = []
        for path in root_folder.rglob("*"):
            if not path.is_file() or path.suffix.lower() != ".cdr":
                continue
            if keyword and keyword not in self._normalize_text(path.name):
                continue

            match = self._score_candidate(path, root_resolved, search_terms)
            if match is None:
                continue

            relative_path = str(path.resolve().relative_to(root_resolved))
            item_id = self._encode_item_id(relative_path)
            preview_url = f"/api/client-assets/preview/{item_id}"
            scored_items.append(
                (
                    match["score"],
                    path.stat().st_mtime,
                    ClientAssetItem(
                        item_id=item_id,
                        name=path.name,
                        relative_path=relative_path,
                        absolute_path=str(path),
                        contains_credito=bool(credito_flag_keyword and credito_flag_keyword in self._normalize_text(path.name)),
                        match_reason=match["reason"],
                        modified_at=path.stat().st_mtime,
                        preview_url=preview_url,
                    ),
                )
            )

        scored_items.sort(key=lambda item: (-item[0], -item[1], item[2].name.lower()))
        return [item for _, _, item in scored_items[:max_files]]

    def _build_cache_path(self, source_path: Path) -> Path:
        cache_dir = self._preview_cache_dir()
        signature = f"{source_path.resolve()}|{source_path.stat().st_mtime_ns}"
        digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()
        filename = f"{source_path.stem}_{digest[:12]}.png"
        return cache_dir / filename

    def _format_preview_stage_error(self, stage: str, exc: Exception) -> str:
        detail = str(exc).strip() or exc.__class__.__name__
        return f"{stage}: {detail}"

    def _extract_embedded_thumbnail(self, source_path: Path, output_path: Path) -> None:
        try:
            from PIL import Image
        except Exception as exc:
            raise RuntimeError("No se pudo cargar Pillow para extraer miniaturas embebidas.") from exc

        candidate_names = [
            "metadata/thumbnails/thumbnail.png",
            "metadata/thumbnail.png",
            "thumbnails/thumbnail.png",
            "thumbnail.png",
            "preview.png",
            "preview.jpg",
            "thumbnail.jpg",
        ]

        try:
            with zipfile.ZipFile(source_path, "r") as archive:
                names = archive.namelist()
                selected_name = None

                for name in candidate_names:
                    if name in names:
                        selected_name = name
                        break

                if selected_name is None:
                    for name in names:
                        lowered = name.lower()
                        if lowered.endswith((".png", ".jpg", ".jpeg")) and "thumb" in lowered:
                            selected_name = name
                            break

                if selected_name is None:
                    raise RuntimeError("El archivo CDR no contiene una miniatura embebida utilizable.")

                image_bytes = archive.read(selected_name)
        except zipfile.BadZipFile as exc:
            raise RuntimeError("El archivo CDR no tiene estructura ZIP compatible para extraer miniatura.") from exc
        except KeyError as exc:
            raise RuntimeError("No se pudo leer la miniatura embebida del archivo CDR.") from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                image.load()
                image.save(output_path, format="PNG")
        except Exception as exc:
            raise RuntimeError("La miniatura embebida existe, pero no se pudo decodificar o guardar como PNG.") from exc

    def _export_cdr_preview_with_corel(self, source_path: Path, output_path: Path) -> None:
        executor = self._preview_executor
        if executor is None:
            raise RuntimeError("La sesion de previews de CorelDRAW no esta disponible.")
        future = executor.submit(self._export_cdr_preview_with_corel_worker, source_path, output_path)
        future.result()

    def _export_cdr_preview_with_corel_worker(self, source_path: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = None
        try:
            app, constants = self._get_or_create_preview_corel_session()
            app.Visible = bool(self.config.get("corel_visible", False))
            try:
                doc = app.OpenDocument(str(source_path))
            except Exception as exc:
                raise RuntimeError(f"CorelDRAW no pudo abrir el documento: {source_path}") from exc

            width = int(self.config.get("preview_width", 1200) or 1200)
            height = int(self.config.get("preview_height", 0) or 0)
            dpi = int(self.config.get("preview_dpi", 120) or 120)

            try:
                export_filter = doc.ExportBitmap(
                    str(output_path),
                    constants.cdrPNG,
                    constants.cdrCurrentPage,
                    constants.cdrRGBColorImage,
                    width,
                    height,
                    dpi,
                    dpi,
                    constants.cdrNormalAntiAliasing,
                    False,
                    False,
                    True,
                    False,
                    constants.cdrCompressionNone,
                    None,
                    None,
                )
            except Exception as exc:
                raise RuntimeError("CorelDRAW abrio el documento, pero fallo al preparar ExportBitmap hacia PNG.") from exc

            try:
                export_filter.Finish()
            except Exception as exc:
                raise RuntimeError("CorelDRAW inicio la exportacion PNG, pero no pudo finalizarla.") from exc

            if not output_path.exists():
                raise RuntimeError("CorelDRAW no dejo ningun PNG generado en la ruta esperada.")
        except Exception as exc:
            raise RuntimeError(f"No se pudo generar preview CDR con CorelDRAW: {exc}") from exc
        finally:
            try:
                if doc is not None:
                    doc.Close()
            except Exception:
                pass

    def _get_or_create_preview_corel_session(self):
        current_thread_id = threading.get_ident()

        if self._preview_app is not None and self._preview_thread_id == current_thread_id:
            try:
                self._preview_app.Visible = bool(self.config.get("corel_visible", False))
                return self._preview_app, self._preview_constants
            except Exception:
                logger.warning("La sesion persistente de CorelDRAW para previews quedo invalida. Se recreara.", exc_info=True)
                self._dispose_preview_corel_session()

        pythoncom, win32_client, constants = self._load_corel_preview_automation()
        try:
            pythoncom.CoInitialize()
            app = win32_client.gencache.EnsureDispatch("CorelDRAW.Application")
            app.Visible = bool(self.config.get("corel_visible", False))
        except Exception as exc:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            raise RuntimeError("No se pudo inicializar la automatizacion COM de CorelDRAW.") from exc

        self._preview_pythoncom = pythoncom
        self._preview_constants = constants
        self._preview_app = app
        self._preview_thread_id = current_thread_id
        return app, constants

    def _dispose_preview_corel_session(self) -> None:
        app = self._preview_app
        pythoncom = self._preview_pythoncom

        self._preview_app = None
        self._preview_pythoncom = None
        self._preview_constants = None
        self._preview_thread_id = None

        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass

        try:
            if pythoncom is not None:
                pythoncom.CoUninitialize()
        except Exception:
            pass

    def _resolve_corel_prepare_profile(self, profile_id: str) -> Dict[str, Any]:
        profiles = self.config.get("corel_prepare_profiles", {}) or {}
        if not isinstance(profiles, dict):
            raise ValueError("corel_prepare_profiles tiene formato invalido.")

        profile = profiles.get(profile_id)
        if not isinstance(profile, dict):
            raise ValueError(f"No existe el perfil de preparacion solicitado: {profile_id}")

        return dict(profile)

    def _get_corel_macro_config(self) -> Dict[str, Any]:
        raw = self.config.get("corel_macro", {}) or {}
        if not isinstance(raw, dict):
            raise ValueError("corel_macro tiene formato invalido.")
        return {
            "enabled": bool(raw.get("enabled", False)),
            "project_name": str(raw.get("project_name", "") or "").strip(),
            "module_name": str(raw.get("module_name", "ClientAssetsPrepare") or "").strip(),
            "entrypoint": str(raw.get("entrypoint", "PrepareClientAsset") or "").strip(),
            "profile_entrypoints": self._sanitize_corel_macro_profile_entrypoints(raw.get("profile_entrypoints", {})),
            "fallback_to_python_prepare": bool(raw.get("fallback_to_python_prepare", True)),
            "debug_enabled": bool(raw.get("debug_enabled", True)),
        }

    def _sanitize_corel_macro_profile_entrypoints(self, raw: Any) -> Dict[str, str]:
        if not isinstance(raw, dict):
            return {}

        sanitized: Dict[str, str] = {}
        for profile_id, entrypoint in raw.items():
            safe_profile_id = str(profile_id or "").strip()
            safe_entrypoint = str(entrypoint or "").strip()
            if not safe_profile_id or not safe_entrypoint:
                continue
            sanitized[safe_profile_id] = safe_entrypoint
        return sanitized

    def _prepare_corel_document(
        self,
        app: Any,
        doc: Any,
        profile_id: str,
        profile: Dict[str, Any],
        source_path: Path,
    ) -> tuple[Dict[str, Any], List[str]]:
        macro_config = self._get_corel_macro_config()
        if not macro_config.get("enabled", False):
            return {"used": False, "status": "disabled"}, []

        try:
            result = self._run_corel_prepare_macro(app, profile_id, source_path, macro_config)
            return result, []
        except Exception as exc:
            if not macro_config.get("fallback_to_python_prepare", True):
                raise RuntimeError(f"No se pudo ejecutar la macro de CorelDRAW para el perfil \"{profile_id}\": {exc}") from exc

            warning = (
                f'No se pudo ejecutar la macro de CorelDRAW para el perfil "{profile_id}". '
                "Se uso fallback de preparacion via COM."
            )
            return {
                "used": False,
                "status": "failed_fallback",
                "error": str(exc),
                "profile_id": profile_id,
                "project_name": macro_config.get("project_name") or None,
                "module_name": macro_config.get("module_name") or None,
                "entrypoint": macro_config.get("entrypoint") or None,
                "debug_enabled": bool(macro_config.get("debug_enabled", True)),
            }, [warning]

    def _run_corel_prepare_macro(
        self,
        app: Any,
        profile_id: str,
        source_path: Path,
        macro_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        module_name = str(macro_config.get("module_name", "") or "").strip()
        entrypoint = self._resolve_corel_macro_entrypoint(profile_id, macro_config)
        project_name = str(macro_config.get("project_name", "") or "").strip()

        if not module_name:
            raise RuntimeError("Falta corel_macro.module_name.")
        if not entrypoint:
            raise RuntimeError("Falta corel_macro.entrypoint.")

        debug_enabled = bool(macro_config.get("debug_enabled", True))
        errors: List[str] = []
        attempts: List[Dict[str, Any]] = []
        for target_name, method_name, args in self._build_corel_macro_call_candidates(
            app,
            project_name,
            module_name,
            entrypoint,
            profile_id,
        ):
            target = app if target_name == "application" else self._safe_getattr(app, target_name)
            method = self._safe_getattr(target, method_name) if target is not None else None
            if not callable(method):
                if debug_enabled:
                    attempts.append(
                        {
                            "target": f"{target_name}.{method_name}",
                            "args": [str(arg) for arg in args],
                            "status": "missing",
                        }
                    )
                continue
            try:
                method(*args)
                result = {
                    "used": True,
                    "status": "executed",
                    "project_name": project_name or None,
                    "module_name": module_name,
                    "entrypoint": entrypoint,
                    "profile_id": profile_id,
                    "target": f"{target_name}.{method_name}",
                    "document": str(source_path),
                }
                if debug_enabled:
                    attempts.append(
                        {
                            "target": f"{target_name}.{method_name}",
                            "args": [str(arg) for arg in args],
                            "status": "ok",
                        }
                    )
                    result["attempts"] = attempts
                return result
            except Exception as exc:
                errors.append(f"{target_name}.{method_name}: {exc}")
                if debug_enabled:
                    attempts.append(
                        {
                            "target": f"{target_name}.{method_name}",
                            "args": [str(arg) for arg in args],
                            "status": "error",
                            "detail": str(exc),
                        }
                    )

        detail = " | ".join(errors) if errors else "No se encontro un metodo COM compatible para ejecutar macros."
        if debug_enabled and attempts:
            detail = f"{detail} | intentos={json.dumps(attempts, ensure_ascii=False)}"
        raise RuntimeError(detail)

    def _resolve_corel_macro_entrypoint(self, profile_id: str, macro_config: Dict[str, Any]) -> str:
        profile_entrypoints = macro_config.get("profile_entrypoints", {}) or {}
        if isinstance(profile_entrypoints, dict):
            selected = str(profile_entrypoints.get(profile_id, "") or "").strip()
            if selected:
                return selected
        return str(macro_config.get("entrypoint", "") or "").strip()

    def _build_corel_macro_call_candidates(
        self,
        app: Any,
        project_name: str,
        module_name: str,
        entrypoint: str,
        profile_id: str,
    ) -> List[tuple[str, str, tuple[Any, ...]]]:
        candidates: List[tuple[str, str, tuple[Any, ...]]] = [
            ("application", "RunMacro", (module_name, entrypoint, profile_id)),
            ("application", "RunMacro", (f"{module_name}.{entrypoint}", profile_id)),
            ("application", "ExecuteMacro", (module_name, entrypoint, profile_id)),
            ("application", "ExecuteMacro", (f"{module_name}.{entrypoint}", profile_id)),
            ("GMSManager", "RunMacro", (f"{module_name}.{entrypoint}", profile_id)),
            ("GMSManager", "RunMacro", (f"{module_name}.{entrypoint}",)),
            ("GMSManager", "RunMacro", (module_name, entrypoint, profile_id)),
            ("GMSManager", "RunMacroEx", (module_name, entrypoint, profile_id)),
            ("GMSManager", "ExecuteMacro", (module_name, entrypoint, profile_id)),
        ]

        project_candidates = self._build_corel_macro_project_candidates(project_name)
        for candidate_project_name in project_candidates:
            candidates = [
                ("GMSManager", "RunMacro", (candidate_project_name, f"{module_name}.{entrypoint}", profile_id)),
                ("GMSManager", "RunMacro", (candidate_project_name, f"{module_name}.{entrypoint}")),
                ("GMSManager", "RunMacroEx", (candidate_project_name, f"{module_name}.{entrypoint}", profile_id)),
                ("GMSManager", "RunMacroEx", (candidate_project_name, f"{module_name}.{entrypoint}")),
                ("GMSManager", "ExecuteMacro", (candidate_project_name, f"{module_name}.{entrypoint}", profile_id)),
                ("GMSManager", "ExecuteMacro", (candidate_project_name, f"{module_name}.{entrypoint}")),
                ("application", "RunMacro", (candidate_project_name, module_name, entrypoint, profile_id)),
                ("application", "RunMacro", (f"{candidate_project_name}.{module_name}.{entrypoint}", profile_id)),
                ("application", "ExecuteMacro", (candidate_project_name, module_name, entrypoint, profile_id)),
                ("application", "ExecuteMacro", (f"{candidate_project_name}.{module_name}.{entrypoint}", profile_id)),
                ("GMSManager", "RunMacro", (f"{candidate_project_name}!{module_name}.{entrypoint}", profile_id)),
                ("GMSManager", "RunMacro", (f"{candidate_project_name}!{module_name}.{entrypoint}",)),
                ("GMSManager", "RunMacro", (f"{candidate_project_name}.{module_name}.{entrypoint}", profile_id)),
                ("GMSManager", "RunMacro", (f"{candidate_project_name}.{module_name}.{entrypoint}",)),
                ("GMSManager", "RunMacro", (candidate_project_name, module_name, entrypoint, profile_id)),
                ("GMSManager", "RunMacroEx", (candidate_project_name, module_name, entrypoint, profile_id)),
                ("GMSManager", "ExecuteMacro", (candidate_project_name, module_name, entrypoint, profile_id)),
            ] + candidates

        return self._dedupe_macro_candidates(candidates)

    def _build_corel_macro_project_candidates(self, project_name: str) -> List[str]:
        raw = str(project_name or "").strip()
        candidates: List[str] = []

        if raw:
            candidates.append(raw)
            if raw.lower().endswith(".gms"):
                candidates.append(raw[:-4])
            else:
                candidates.append(f"{raw}.gms")
        else:
            candidates.extend(["GlobalMacros.gms", "GlobalMacros"])

        seen = set()
        ordered: List[str] = []
        for candidate in candidates:
            normalized = candidate.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(normalized)
        return ordered

    def _dedupe_macro_candidates(
        self,
        candidates: List[tuple[str, str, tuple[Any, ...]]],
    ) -> List[tuple[str, str, tuple[Any, ...]]]:
        seen = set()
        deduped: List[tuple[str, str, tuple[Any, ...]]] = []
        for target_name, method_name, args in candidates:
            key = (target_name, method_name, tuple(str(arg) for arg in args))
            if key in seen:
                continue
            seen.add(key)
            deduped.append((target_name, method_name, args))
        return deduped

    def _apply_corel_prepare_profile(
        self,
        app: Any,
        doc: Any,
        profile_id: str,
        profile: Dict[str, Any],
    ) -> tuple[Dict[str, Any], List[str]]:
        warnings: List[str] = []
        applied_settings: Dict[str, Any] = {}
        targets = self._build_corel_prepare_targets(app, doc)

        configured_fields = [
            ("printer_name", ["PrinterName", "Printer"], ["SetPrinter", "SelectPrinter"]),
            ("paper_name", ["PaperName", "Paper", "PaperSize"], ["SetPaper", "SelectPaper"]),
            ("orientation", ["Orientation", "PrintOrientation"], ["SetOrientation"]),
            ("print_profile_name", ["PrintProfileName", "PrintStyle", "PrintProfile"], ["ApplyPrintProfile", "LoadPrintProfile", "SelectPrintProfile"]),
        ]

        for field_name, property_candidates, method_candidates in configured_fields:
            raw_value = str(profile.get(field_name, "") or "").strip()
            if not raw_value:
                warnings.append(f'El perfil "{profile_id}" no define {field_name}.')
                continue

            applied_target = self._apply_corel_prepare_setting(
                targets,
                raw_value,
                property_candidates,
                method_candidates,
            )
            if applied_target:
                applied_settings[field_name] = {
                    "value": raw_value,
                    "target": applied_target,
                }
            else:
                warnings.append(
                    f'No se pudo aplicar {field_name} del perfil "{profile_id}". Revisar soporte COM/CorelDRAW 24.'
                )

        note = str(profile.get("notes", "") or "").strip()
        if note:
            applied_settings["notes"] = note

        return applied_settings, warnings

    def _build_corel_prepare_targets(self, app: Any, doc: Any) -> List[tuple[str, Any]]:
        targets: List[tuple[str, Any]] = [("document", doc)]
        for attr_name in ("PrintSettings", "PrintOptions", "Print"):
            target = self._safe_getattr(doc, attr_name)
            if target is not None:
                targets.append((f"document.{attr_name}", target))

        targets.append(("application", app))
        for attr_name in ("PrintSettings", "PrintOptions", "Print"):
            target = self._safe_getattr(app, attr_name)
            if target is not None:
                targets.append((f"application.{attr_name}", target))
        return targets

    def _safe_getattr(self, target: Any, attr_name: str) -> Any:
        try:
            return getattr(target, attr_name)
        except Exception:
            return None

    def _apply_corel_prepare_setting(
        self,
        targets: List[tuple[str, Any]],
        value: Any,
        property_candidates: List[str],
        method_candidates: List[str],
    ) -> Optional[str]:
        for target_name, target in targets:
            for property_name in property_candidates:
                try:
                    setattr(target, property_name, value)
                    return f"{target_name}.{property_name}"
                except Exception:
                    continue

            for method_name in method_candidates:
                method = self._safe_getattr(target, method_name)
                if not callable(method):
                    continue
                try:
                    method(value)
                    return f"{target_name}.{method_name}()"
                except Exception:
                    continue
        return None

    def _load_corel_open_automation(self):
        try:
            import pythoncom
            import win32com.client  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "No se pudo cargar pywin32/Corel automation. Instala pywin32 y ejecuta este endpoint en la PC con CorelDRAW."
            ) from exc
        return pythoncom, win32com.client

    def _load_corel_preview_automation(self):
        try:
            import pythoncom
            import win32com.client  # type: ignore
            from win32com.client import constants  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "No se pudo cargar pywin32/Corel automation. Instala pywin32 y ejecuta este endpoint en la PC con CorelDRAW."
            ) from exc
        return pythoncom, win32com.client, constants

    def _bring_corel_to_front(self, source_path: Path) -> Optional[str]:
        try:
            import win32con  # type: ignore
            import win32gui  # type: ignore
        except Exception:
            return "El archivo se abrio, pero no se pudo traer CorelDRAW al frente automaticamente."

        normalized_titles = [
            "CORELDRAW",
            self._normalize_text_with_spaces(source_path.stem),
            self._normalize_text_with_spaces(source_path.name),
        ]
        matches: List[tuple[int, str]] = []

        def collect_windows(hwnd, _extra) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = str(win32gui.GetWindowText(hwnd) or "").strip()
            if not title:
                return
            normalized_title = self._normalize_text_with_spaces(title)
            if any(candidate and candidate in normalized_title for candidate in normalized_titles):
                matches.append((hwnd, title))

        try:
            win32gui.EnumWindows(collect_windows, None)
            if not matches:
                return "El archivo se abrio, pero no se encontro la ventana de CorelDRAW para ponerla al frente."

            matches.sort(
                key=lambda item: (
                    0 if self._normalize_text_with_spaces(source_path.name) in self._normalize_text_with_spaces(item[1]) else 1,
                    0 if "CORELDRAW" in self._normalize_text_with_spaces(item[1]) else 1,
                    item[1].lower(),
                )
            )
            hwnd = matches[0][0]
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            return None
        except Exception:
            return "El archivo se abrio, pero no se pudo traer CorelDRAW al frente automaticamente."

    def _normalize_text(self, text: Any) -> str:
        normalized = unicodedata.normalize("NFKD", str(text or "").strip())
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.upper()
        return "".join(ch for ch in normalized if ch.isalnum())

    def _normalize_text_with_spaces(self, text: Any) -> str:
        normalized = unicodedata.normalize("NFKD", str(text or "").strip())
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.upper()
        normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _build_search_terms(self, client_name: str, match_mode: str = "strict") -> Dict[str, Any]:
        spaced = self._normalize_text_with_spaces(client_name)
        tokens = [token for token in spaced.split(" ") if token]
        stopwords = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "SA", "SRL"}
        significant_tokens = [token for token in tokens if len(token) >= 3 and token not in stopwords]
        compact = "".join(tokens)
        acronym = self._build_acronym(significant_tokens)
        if not acronym and len(tokens) == 1 and len(tokens[0]) <= 6:
            acronym = tokens[0]

        effective_tokens = significant_tokens or tokens
        token_count = len(effective_tokens)
        if token_count <= 1:
            min_token_hits = 1
        elif token_count <= 3:
            min_token_hits = token_count
        else:
            min_token_hits = max(2, math.ceil(token_count * 0.6))

        return {
            "match_mode": str(match_mode or "strict").strip().lower(),
            "spaced": spaced,
            "compact": compact,
            "acronym": acronym,
            "tokens": effective_tokens,
            "min_token_hits": min_token_hits,
        }

    def _score_candidate(self, path: Path, root_folder: Path, search_terms: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        filename_spaced = self._normalize_text_with_spaces(path.stem)
        filename_normalized = self._normalize_text(path.stem)
        relative_path = path.resolve().relative_to(root_folder)
        relative_parent = relative_path.parent
        path_spaced = self._normalize_text_with_spaces(str(relative_path))
        path_normalized = self._normalize_text(str(relative_path))
        path_terms = self._build_search_terms(str(relative_parent))
        path_acronym = str(path_terms.get("acronym", "") or "")
        path_compact = str(path_terms.get("compact", "") or "")
        compact = str(search_terms.get("compact", "") or "")
        acronym = str(search_terms.get("acronym", "") or "")
        tokens = list(search_terms.get("tokens", []) or [])
        min_token_hits = int(search_terms.get("min_token_hits", 1) or 1)
        match_mode = str(search_terms.get("match_mode", "strict") or "strict").strip().lower()

        filename_words = set(filename_spaced.split(" "))
        path_words = set(path_spaced.split(" "))
        filename_token_hits = [token for token in tokens if token and token in filename_words]
        path_token_hits = [token for token in tokens if token and token in path_words]
        all_tokens_hit_in_filename = bool(tokens) and len(filename_token_hits) == len(tokens)
        all_tokens_hit_in_path = bool(tokens) and len(path_token_hits) == len(tokens)

        if acronym and acronym in filename_normalized:
            return {"score": 560 + len(acronym), "reason": "acronym", "tier": 5}

        if compact and compact == filename_normalized:
            return {"score": 540 + len(compact), "reason": "full_name", "tier": 5}

        if compact and compact in filename_normalized:
            return {"score": 520 + len(compact), "reason": "full_name", "tier": 5}

        if all_tokens_hit_in_filename:
            return {"score": 500 + sum(len(token) for token in filename_token_hits), "reason": "token", "tier": 4}

        if filename_token_hits and len(filename_token_hits) >= min_token_hits:
            return {"score": 340 + sum(len(token) for token in filename_token_hits), "reason": "token", "tier": 3}

        if acronym and acronym in path_normalized:
            return {"score": 460 + len(acronym), "reason": "path_hint", "tier": 4}

        if acronym and path_acronym and acronym == path_acronym:
            return {"score": 455 + len(acronym), "reason": "path_hint", "tier": 4}

        if compact and compact == path_compact:
            return {"score": 450 + len(compact), "reason": "path_hint", "tier": 4}

        if compact and compact in path_normalized:
            return {"score": 430 + len(compact), "reason": "path_hint", "tier": 4}

        if all_tokens_hit_in_path:
            return {"score": 410 + sum(len(token) for token in path_token_hits), "reason": "path_hint", "tier": 4}

        if path_token_hits and len(path_token_hits) >= min_token_hits:
            return {"score": 280 + sum(len(token) for token in path_token_hits), "reason": "path_hint", "tier": 3}

        if match_mode == "broad":
            loose_filename_hits = [token for token in tokens if token and token in filename_normalized]
            if loose_filename_hits:
                return {"score": 220 + sum(len(token) for token in loose_filename_hits), "reason": "token", "tier": 2}

            loose_path_hits = [token for token in tokens if token and token in path_normalized]
            if loose_path_hits:
                return {"score": 120 + sum(len(token) for token in loose_path_hits), "reason": "path_hint", "tier": 1}

        return None

    def _collect_matched_directories(self, root_folder: Path, items: List[ClientAssetItem]) -> List[str]:
        directories: List[str] = []
        seen = set()
        root_resolved = root_folder.resolve()
        for item in items:
            parent = Path(item.absolute_path).resolve().parent
            if parent in seen:
                continue
            seen.add(parent)
            try:
                rel_parent = str(parent.relative_to(root_resolved))
            except ValueError:
                rel_parent = str(parent)
            directories.append(rel_parent)
        return directories

    def _build_acronym(self, tokens: List[str]) -> str:
        filtered = [token for token in tokens if token]
        if len(filtered) <= 1:
            return ""
        return "".join(token[0] for token in filtered)

    def _encode_item_id(self, relative_path: str) -> str:
        raw = relative_path.replace("\\", "/").encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _decode_item_id(self, item_id: str) -> str:
        padding = "=" * ((4 - len(item_id) % 4) % 4)
        raw = base64.urlsafe_b64decode((item_id + padding).encode("ascii"))
        return raw.decode("utf-8").replace("/", os.sep)


client_assets_service = ClientAssetsService()
