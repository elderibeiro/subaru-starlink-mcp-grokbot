"""Load MySubaru credentials from env or `pass`. Never log values."""

from __future__ import annotations

import os
import secrets as pysecrets
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PASS_USERNAME = "subaru/username"
PASS_PASSWORD = "subaru/password"
PASS_PIN = "subaru/pin"
PASS_DEVICE_ID = "subaru/device-id"

ENV_USERNAME = "SUBARU_USERNAME"
ENV_PASSWORD = "SUBARU_PASSWORD"
ENV_PIN = "SUBARU_PIN"
ENV_DEVICE_ID = "SUBARU_DEVICE_ID"
ENV_DEVICE_NAME = "SUBARU_DEVICE_NAME"
ENV_COUNTRY = "SUBARU_COUNTRY"
ENV_NICKNAME = "SUBARU_NICKNAME"

DEFAULT_DEVICE_NAME = "grok-bot"
DEFAULT_COUNTRY = "USA"

SHARE_DIR = Path.home() / ".local" / "share" / "subaru-mcp"
DEVICE_ID_FILE = SHARE_DIR / "device_id"

_PASS_TIMEOUT = 12


@dataclass(frozen=True)
class Credentials:
    username: str | None
    password: str | None
    pin: str | None
    device_id: str | None
    device_name: str
    country: str
    nickname: str | None

    def configured(self) -> bool:
        return bool(self.username and self.password and self.pin and self.device_id)

    def secret_values(self) -> tuple[str, ...]:
        """Values long enough to globally redact (PIN is excluded)."""
        vals = []
        for item in (self.username, self.password, self.device_id):
            if item and len(item) >= 6:
                vals.append(item)
        return tuple(vals)


def _pass_get(key: str) -> str | None:
    try:
        proc = subprocess.run(
            ["pass", key],
            check=False,
            capture_output=True,
            text=True,
            timeout=_PASS_TIMEOUT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").splitlines()
    if not line:
        return None
    value = line[0].strip()
    return value or None


def _pass_insert(key: str, value: str) -> bool:
    try:
        proc = subprocess.run(
            ["pass", "insert", "-e", key],
            check=False,
            input=value + "\n",
            capture_output=True,
            text=True,
            timeout=_PASS_TIMEOUT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def _read_device_id_file() -> str | None:
    try:
        if not DEVICE_ID_FILE.is_file():
            return None
        text = DEVICE_ID_FILE.read_text(encoding="utf-8").strip()
        return text or None
    except OSError:
        return None


def _write_device_id_file(device_id: str) -> None:
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(SHARE_DIR, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(DEVICE_ID_FILE, flags, 0o600)
    try:
        os.write(fd, (device_id + "\n").encode("utf-8"))
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        os.close(fd)


def generate_device_id() -> str:
    """Stable integer as decimal string. Not printed by callers."""
    return str(int(time.time() * 1000) + pysecrets.randbelow(10**6))


def ensure_device_id() -> str | None:
    """Return a device id from env, pass, file, or generate-once."""
    env = (os.environ.get(ENV_DEVICE_ID) or "").strip()
    if env:
        return env
    stored = _pass_get(PASS_DEVICE_ID) or _read_device_id_file()
    if stored:
        os.environ.setdefault(ENV_DEVICE_ID, stored)
        if not DEVICE_ID_FILE.is_file():
            try:
                _write_device_id_file(stored)
            except OSError:
                pass
        return stored
    new_id = generate_device_id()
    try:
        _write_device_id_file(new_id)
    except OSError:
        sys.stderr.write("subaru-mcp: could not write device_id file\n")
        return None
    _pass_insert(PASS_DEVICE_ID, new_id)
    os.environ[ENV_DEVICE_ID] = new_id
    sys.stderr.write("subaru-mcp: generated device_id (value not logged)\n")
    return new_id


def load_credentials() -> Credentials:
    """Env overrides pass. Missing fields stay None; callers must not crash."""
    ensure_device_id()
    username = (os.environ.get(ENV_USERNAME) or "").strip() or _pass_get(PASS_USERNAME)
    password = (os.environ.get(ENV_PASSWORD) or "").strip() or _pass_get(PASS_PASSWORD)
    pin = (os.environ.get(ENV_PIN) or "").strip() or _pass_get(PASS_PIN)
    device_id = (os.environ.get(ENV_DEVICE_ID) or "").strip() or _pass_get(PASS_DEVICE_ID) or _read_device_id_file()
    device_name = (os.environ.get(ENV_DEVICE_NAME) or "").strip() or DEFAULT_DEVICE_NAME
    country = (os.environ.get(ENV_COUNTRY) or "").strip() or DEFAULT_COUNTRY
    nickname = (os.environ.get(ENV_NICKNAME) or "").strip() or None
    return Credentials(
        username=username,
        password=password,
        pin=pin,
        device_id=device_id,
        device_name=device_name,
        country=country,
        nickname=nickname,
    )


def load_into_environ() -> Credentials:
    """Populate env from pass for the MCP child. Values are never printed."""
    creds = load_credentials()
    if creds.username and not os.environ.get(ENV_USERNAME):
        os.environ[ENV_USERNAME] = creds.username
    if creds.password and not os.environ.get(ENV_PASSWORD):
        os.environ[ENV_PASSWORD] = creds.password
    if creds.pin and not os.environ.get(ENV_PIN):
        os.environ[ENV_PIN] = creds.pin
    if creds.device_id and not os.environ.get(ENV_DEVICE_ID):
        os.environ[ENV_DEVICE_ID] = creds.device_id
    os.environ.setdefault(ENV_DEVICE_NAME, creds.device_name)
    os.environ.setdefault(ENV_COUNTRY, creds.country)
    if creds.nickname:
        os.environ.setdefault(ENV_NICKNAME, creds.nickname)
    return creds


def missing_pass_keys(creds: Credentials) -> list[str]:
    missing = []
    if not creds.username:
        missing.append(PASS_USERNAME)
    if not creds.password:
        missing.append(PASS_PASSWORD)
    if not creds.pin:
        missing.append(PASS_PIN)
    if not creds.device_id:
        missing.append(PASS_DEVICE_ID)
    return missing
