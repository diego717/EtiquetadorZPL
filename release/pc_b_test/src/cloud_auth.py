"""
Auth service for cloud-style access with signed bearer tokens.
This module is intentionally self-contained to avoid extra dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class CloudAuthService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.config_path = self._resolve_config_path()
        self.config = self._load_or_create_config()

    def _resolve_config_path(self) -> Path:
        if os.name == "nt":
            base_dir = Path(os.environ.get("APPDATA", "."))
        else:
            base_dir = Path.home() / ".config"
        config_dir = base_dir / "EtiquetadorZPL"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "cloud_auth.json"

    def _load_or_create_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if "secret_key" in data and "users" in data:
                    return data
            except Exception:
                pass

        admin_user = os.environ.get("ETIQUETADOR_ADMIN_USER", "admin")
        admin_pass = os.environ.get("ETIQUETADOR_ADMIN_PASS", "admin123")
        config = {
            "secret_key": secrets.token_urlsafe(48),
            "token_ttl_seconds": 8 * 60 * 60,
            "users": {
                admin_user: {
                    "password_hash": self.hash_password(admin_pass),
                    "role": "admin",
                    "enabled": True,
                    "created_at": int(time.time()),
                }
            },
        }
        self._save_config(config)
        return config

    def _save_config(self, data: Optional[Dict[str, Any]] = None) -> None:
        payload = data if data is not None else self.config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _b64url_decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))

    def hash_password(self, password: str, salt: Optional[bytes] = None) -> str:
        if salt is None:
            salt = os.urandom(16)
        iterations = 120000
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return (
            f"pbkdf2_sha256${iterations}$"
            f"{self._b64url_encode(salt)}${self._b64url_encode(digest)}"
        )

    def verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            algo, iterations_str, salt_b64, digest_b64 = stored_hash.split("$", 3)
            if algo != "pbkdf2_sha256":
                return False
            iterations = int(iterations_str)
            salt = self._b64url_decode(salt_b64)
            expected = self._b64url_decode(digest_b64)
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                iterations,
            )
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            user = self.config.get("users", {}).get(username)
            if not user or not user.get("enabled", True):
                return None
            if not self.verify_password(password, user.get("password_hash", "")):
                return None
            return {
                "username": username,
                "role": user.get("role", "user"),
            }

    def issue_token(self, username: str, role: str, ttl_seconds: Optional[int] = None) -> str:
        now = int(time.time())
        ttl = int(ttl_seconds or self.config.get("token_ttl_seconds", 8 * 60 * 60))
        payload = {
            "sub": username,
            "role": role,
            "iat": now,
            "exp": now + ttl,
            "iss": "EtiquetadorZPL",
        }
        payload_b64 = self._b64url_encode(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        )
        signature = hmac.new(
            self.config["secret_key"].encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{payload_b64}.{self._b64url_encode(signature)}"

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            payload_b64, sig_b64 = token.split(".", 1)
            expected = hmac.new(
                self.config["secret_key"].encode("utf-8"),
                payload_b64.encode("ascii"),
                hashlib.sha256,
            ).digest()
            provided = self._b64url_decode(sig_b64)
            if not hmac.compare_digest(expected, provided):
                return None
            payload = json.loads(self._b64url_decode(payload_b64).decode("utf-8"))
            if int(payload.get("exp", 0)) < int(time.time()):
                return None
            username = payload.get("sub", "")
            role = payload.get("role", "")
            if not username or not role:
                return None
            with self._lock:
                user = self.config.get("users", {}).get(username)
                if not user or not user.get("enabled", True):
                    return None
            return payload
        except Exception:
            return None

    def create_user(self, username: str, password: str, role: str = "agent") -> Dict[str, Any]:
        normalized = (username or "").strip()
        if not normalized:
            raise ValueError("Username vacio")
        if len(password or "") < 8:
            raise ValueError("Password debe tener al menos 8 caracteres")
        if role not in {"admin", "agent"}:
            raise ValueError("Role invalido. Usa admin o agent")

        with self._lock:
            users = self.config.setdefault("users", {})
            if normalized in users:
                raise ValueError("El usuario ya existe")
            users[normalized] = {
                "password_hash": self.hash_password(password),
                "role": role,
                "enabled": True,
                "created_at": int(time.time()),
            }
            self._save_config()
            return {
                "username": normalized,
                "role": role,
                "enabled": True,
            }

    def list_users(self) -> List[Dict[str, Any]]:
        with self._lock:
            users = self.config.get("users", {})
            return [
                {
                    "username": username,
                    "role": data.get("role", "agent"),
                    "enabled": bool(data.get("enabled", True)),
                    "created_at": data.get("created_at"),
                }
                for username, data in users.items()
            ]

    def update_password(self, username: str, new_password: str) -> bool:
        if len(new_password or "") < 8:
            raise ValueError("Password debe tener al menos 8 caracteres")
        with self._lock:
            users = self.config.get("users", {})
            if username not in users:
                return False
            users[username]["password_hash"] = self.hash_password(new_password)
            self._save_config()
            return True


cloud_auth_service = CloudAuthService()
