"""Redact credentials, tokens, and VINs from logs and tool output."""

from __future__ import annotations

import re
from collections.abc import Iterable

# Keys that must never appear with values in logs or tool text.
_KV_RE = re.compile(
    r"(?i)\b(password|secret|token|pin|cookie|vin|username)\s*[=:]\s*([^\s,;]+)"
)
# Typical 17-character VIN (I, O, Q excluded).
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
# Bearer / session cookie blobs.
_BEARER_RE = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]+")


def _kv_sub(match: re.Match[str]) -> str:
    return f"{match.group(1)}=***"


def redact(text: str, extra: Iterable[str] | None = None) -> str:
    """Return *text* with secrets and VINs replaced.

    Short values (e.g. a 4-digit PIN) are only removed via key=value patterns,
    never via global replace, so odometer/range numbers stay intact.
    """
    if not text:
        return text
    out = _KV_RE.sub(_kv_sub, text)
    out = _VIN_RE.sub("[VIN]", out)
    out = _BEARER_RE.sub(r"\1 ***", out)
    for secret in extra or ():
        if not secret:
            continue
        if len(secret) < 6:
            continue
        out = out.replace(secret, "***")
    return out
