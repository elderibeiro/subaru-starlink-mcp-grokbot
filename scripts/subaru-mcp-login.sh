#!/bin/sh
# First-run MySubaru 2FA helper. Does not echo passwords or print VINs.
# Does not send lock, unlock, or remote-start commands.
set -eu
HOME_DIR="${GROK_HOME:-${HOME:?HOME is not set}}"
VENV="${SUBARU_MCP_PYTHON:-$HOME_DIR/.local/opt/subaru-mcp/.venv/bin/python3}"
SRC="${SUBARU_MCP_SRC:-$HOME_DIR/.local/opt/subaru-mcp/src}"
echo "Subaru STARLINK MCP login helper"
echo "Insert MySubaru secrets with pass (do not paste them into chat):"
echo "  pass insert -e subaru/username"
echo "  pass insert -e subaru/password"
echo "  pass insert -e subaru/pin"
echo "device_id is generated automatically if missing."
echo
export PYTHONPATH="$SRC${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV" -m subaru_mcp.login
