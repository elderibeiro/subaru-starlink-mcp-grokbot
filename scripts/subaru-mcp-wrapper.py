#!/usr/bin/env python3
"""Launch Subaru STARLINK MCP over stdio. Secrets come from `pass`, never argv."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HOME = Path(os.environ.get("GROK_HOME") or os.path.expanduser("~"))
SRC = os.environ.get(
    "SUBARU_MCP_SRC",
    str(HOME / ".local/opt/subaru-mcp/src"),
)
VENV_PY = os.environ.get(
    "SUBARU_MCP_PYTHON",
    str(HOME / ".local/opt/subaru-mcp/.venv/bin/python3"),
)

sys.path.insert(0, SRC)

from subaru_mcp.secrets import load_into_environ  # noqa: E402


def main() -> None:
    # Load pass -> env. Missing secrets must not crash the stdio handshake.
    try:
        load_into_environ()
    except Exception:  # noqa: BLE001
        sys.stderr.write(
            "subaru-mcp-wrapper: credential load failed; tools will return AUTH_NOT_CONFIGURED\n"
        )
    os.environ["PYTHONPATH"] = SRC + os.pathsep + os.environ.get("PYTHONPATH", "")
    os.execv(VENV_PY, [VENV_PY, "-m", "subaru_mcp"])


if __name__ == "__main__":
    main()
