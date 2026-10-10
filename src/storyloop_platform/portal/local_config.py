"""Per-user portal settings and Windows-protected local credentials."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
from uuid import uuid4


class LocalPreferences:
    """Keep paths in JSON and protect model keys/session tokens with Windows DPAPI."""

    def __init__(self, directory: str | Path | None = None) -> None:
        configured = directory or os.environ.get("STORY_PORTAL_HOME")
        if configured is not None:
            self.directory = Path(configured).expanduser().resolve()
        elif os.name == "nt":
            self.directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "StoryLoop"
        else:
            self.directory = Path.home() / ".config" / "storyloop"

    def load_settings(self) -> dict[str, str]:
        path = self.directory / "settings.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported local portal settings")
        return {key: value for key, value in data.items()
                if key in {"catalog", "config", "db"} and isinstance(value, str)}

    def save_settings(self, catalog: str | Path, config: str | Path | None, db: str | Path) -> None:
        payload = {"schema_version": 1, "catalog": str(Path(catalog).resolve()),
                   "db": str(Path(db).resolve())}
        if config is not None:
            payload["config"] = str(Path(config).resolve())
        self._write(self.directory / "settings.json",
                    json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    def model_key(self, env_name: str) -> str | None:
        return self._secrets().get("model_keys", {}).get(env_name)

    def save_model_key(self, env_name: str, value: str) -> None:
        if not value:
            raise ValueError("model key must not be empty")
        secrets = self._secrets()
        secrets.setdefault("model_keys", {})[env_name] = value
        self._save_secrets(secrets)

    def activate_model_key(self, env_name: str, *, prompt: bool = False,
                           persist: bool = True) -> bool:
        current = os.environ.get(env_name, "").strip()
        if current:
            if persist and current != self.model_key(env_name):
                self.save_model_key(env_name, current)
            return True
        stored = self.model_key(env_name)
        if stored:
            os.environ[env_name] = stored
            return True
        if prompt:
            entered = getpass.getpass(f"{env_name} API Key（输入不回显）: ").strip()
            if entered:
                os.environ[env_name] = entered
                if persist:
                    self.save_model_key(env_name, entered)
                return True
        return False

    def session(self, db: str | Path) -> dict[str, str] | None:
        value = self._secrets().get("sessions", {}).get(str(Path(db).resolve()))
        return value if isinstance(value, dict) else None

    def save_session(self, db: str | Path, username: str, token: str) -> None:
        secrets = self._secrets()
        secrets.setdefault("sessions", {})[str(Path(db).resolve())] = {
            "username": username, "token": token,
        }
        self._save_secrets(secrets)

    def clear_session(self, db: str | Path) -> None:
        secrets = self._secrets()
        sessions = secrets.get("sessions")
        if isinstance(sessions, dict):
            sessions.pop(str(Path(db).resolve()), None)
            self._save_secrets(secrets)

    def _secrets(self) -> dict:
        if os.name != "nt":
            return {}
        path = self.directory / "credentials.dpapi"
        if not path.exists():
            return {}
        try:
            import pywintypes
            import win32crypt
        except ImportError:
            return {}
        try:
            _, clear = win32crypt.CryptUnprotectData(path.read_bytes(), None, None, None, 0)
            data = json.loads(clear.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (pywintypes.error, OSError, ValueError, TypeError):
            return {}

    def _save_secrets(self, secrets: dict) -> None:
        if os.name != "nt":
            return
        try:
            import win32crypt
        except ImportError as error:
            raise RuntimeError("Windows credential persistence requires pywin32") from error
        clear = json.dumps(secrets, ensure_ascii=False).encode("utf-8")
        encrypted = win32crypt.CryptProtectData(clear, "StoryLoop", None, None, None, 0)
        self._write(self.directory / "credentials.dpapi", encrypted)

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
