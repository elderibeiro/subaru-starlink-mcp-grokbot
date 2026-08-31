"""MCP stdio server. Official SDK MCPServer (FastMCP successor in mcp 2.x)."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from subaru_mcp.redact import redact
from subaru_mcp.session import SubaruSession

INSTRUCTIONS = """\
Local-first MySubaru / STARLINK telematics MCP for a USA/Canada Subaru.

This is NOT OBD-II. Readings come from MySubaru Connected Services (formerly STARLINK)
and are often stale until subaru_refresh_status or subaru_locate wakes the vehicle.

Control tools (lock, unlock, remote start/stop, horn, lights) are vehicle-control
operations. Do not call them unless the user explicitly requested that exact action.
Do not infer a lock/unlock/start from chatty context.

Never request, accept, or return a VIN, password, PIN, token, or cookie.
Remote start and lock require an active MySubaru Security / Companion+ plan and
vehicle feature RES. 2021 Crosstrek Sport is g2 gasoline (not PHEV). Heated seats
cannot be activated remotely on Crosstrek (ignored by the vehicle).
"""

VehicleArg = Annotated[
    str | None,
    Field(
        default=None,
        description=(
            "Optional MySubaru vehicle nickname. Needed only when the account has "
            "multiple vehicles. Never pass a VIN."
        ),
    ),
]


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(str(record.msg))
            if record.args:
                record.args = tuple(redact(str(a)) if isinstance(a, str) else a for a in record.args)
        except Exception:  # noqa: BLE001
            return True
        return True


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("subaru_mcp: %(message)s"))
    handler.addFilter(_RedactFilter())
    root = logging.getLogger("subaru_mcp")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    sl = logging.getLogger("subarulink")
    sl.setLevel(logging.WARNING)
    sl.addFilter(_RedactFilter())


_configure_logging()

_session = SubaruSession()


@asynccontextmanager
async def _lifespan(_server: MCPServer) -> AsyncIterator[dict[str, Any]]:
    try:
        yield {}
    finally:
        await get_session().aclose()


mcp = MCPServer(
    "subaru-starlink",
    instructions=INSTRUCTIONS,
    version="0.1.0",
    lifespan=_lifespan,
)


def get_session() -> SubaruSession:
    return _session


def set_session(session: SubaruSession) -> None:
    global _session
    _session = session


@mcp.tool()
async def subaru_status(vehicle: VehicleArg = None) -> str:
    """Compact MySubaru telematics snapshot (not OBD-II): lock if known, ignition, fuel range, odometer, TPMS if present, nickname, model year/name, subscription/RES flags, data freshness. Never returns a VIN. Uses cached server data; does not wake the vehicle."""
    return await get_session().status(vehicle, wake=False)


@mcp.tool()
async def subaru_refresh_status(vehicle: VehicleArg = None) -> str:
    """Wake the vehicle via MySubaru update() then return the same compact telematics snapshot as subaru_status. This contacts the car and can drain the 12V battery if overused. Not OBD-II. Never returns a VIN."""
    return await get_session().status(vehicle, wake=True)


@mcp.tool()
async def subaru_list_climate_presets(vehicle: VehicleArg = None) -> str:
    """List MySubaru climate preset names used with remote start. Names only. Never returns a VIN."""
    return await get_session().list_climate_presets(vehicle)


@mcp.tool()
async def subaru_get_climate_preset(
    name: Annotated[str, Field(description="Climate preset name (case-insensitive).")],
    vehicle: VehicleArg = None,
) -> str:
    """Return a sanitized climate preset (name and user-visible climate fields). If the name is missing, returns INVALID_PRESET plus available names. Never returns a VIN. Crosstrek heated seats cannot be activated remotely."""
    return await get_session().get_climate_preset(name, vehicle)


@mcp.tool()
async def subaru_locate(vehicle: VehicleArg = None) -> str:
    """Wake the vehicle then return latitude/longitude only if MySubaru LOCATION_VALID is true. Otherwise stale/unavailable. Telematics GPS, not OBD-II. Never returns a VIN. Waking the vehicle can drain the 12V battery if overused."""
    return await get_session().locate(vehicle)


@mcp.tool()
async def subaru_tire_pressure(vehicle: VehicleArg = None) -> str:
    """Tire pressures from MySubaru telematics if the vehicle has TPMS; otherwise UNSUPPORTED. Not OBD-II. Never returns a VIN."""
    return await get_session().tire_pressure(vehicle)


@mcp.tool()
async def subaru_fuel_status(vehicle: VehicleArg = None) -> str:
    """Fuel range and average consumption from MySubaru telematics (not OBD-II). Never returns a VIN."""
    return await get_session().fuel_status(vehicle)


@mcp.tool()
async def subaru_odometer(vehicle: VehicleArg = None) -> str:
    """Odometer from MySubaru telematics (not OBD-II). Never returns a VIN."""
    return await get_session().odometer(vehicle)


@mcp.tool()
async def subaru_lock(vehicle: VehicleArg = None) -> str:
    """Lock the vehicle doors via MySubaru remote services. This is a vehicle-control operation. Do not call this unless the user explicitly requested this exact action. Requires MySubaru Security/Companion+. Never pass a VIN, PIN, or password."""
    return await get_session().lock(vehicle)


@mcp.tool()
async def subaru_unlock(vehicle: VehicleArg = None) -> str:
    """Unlock the vehicle doors via MySubaru remote services. This is a vehicle-control operation. Do not call this unless the user explicitly requested this exact action. An explicit unlock request is required; do not infer unlock from chatty context. Requires MySubaru Security/Companion+. Never pass a VIN, PIN, or password."""
    return await get_session().unlock(vehicle)


@mcp.tool()
async def subaru_remote_start(
    preset_name: Annotated[
        str,
        Field(
            description=(
                "Exact MySubaru climate preset name. Matched case-insensitively after trim. "
                "If it does not match an available preset, remote start is not sent."
            ),
        ),
    ],
    vehicle: VehicleArg = None,
) -> str:
    """Remote-start the engine using a named MySubaru climate preset. This is a vehicle-control operation. Do not call this unless the user explicitly requested this exact action. Lists presets and requires an exact name match (case-insensitive trim); never substitutes a different preset. Requires MySubaru Security/Companion+ and vehicle feature RES. 2021 Crosstrek Sport is g2 gas; heated seats cannot be activated remotely. Never pass a VIN, PIN, or password."""
    return await get_session().remote_start(preset_name, vehicle)


@mcp.tool()
async def subaru_remote_stop(vehicle: VehicleArg = None) -> str:
    """Stop a remote-started engine via MySubaru. This is a vehicle-control operation. Do not call this unless the user explicitly requested this exact action. Requires MySubaru Security/Companion+ and RES. Never pass a VIN, PIN, or password."""
    return await get_session().remote_stop(vehicle)


@mcp.tool()
async def subaru_horn(vehicle: VehicleArg = None) -> str:
    """Sound the vehicle horn via MySubaru. This is a vehicle-control operation. Do not call this unless the user explicitly requested this exact action. Requires MySubaru Security/Companion+. Never pass a VIN, PIN, or password."""
    return await get_session().horn(vehicle)


@mcp.tool()
async def subaru_flash_lights(vehicle: VehicleArg = None) -> str:
    """Flash the vehicle lights via MySubaru lights(). This is a vehicle-control operation. Do not call this unless the user explicitly requested this exact action. Requires MySubaru Security/Companion+. Never pass a VIN, PIN, or password."""
    return await get_session().flash_lights(vehicle)


@mcp.tool()
async def subaru_horn_stop(vehicle: VehicleArg = None) -> str:
    """Stop the horn via MySubaru horn_stop(). This is a vehicle-control operation. Do not call this unless the user explicitly requested this exact action. Requires MySubaru Security/Companion+. Never pass a VIN, PIN, or password."""
    return await get_session().horn_stop(vehicle)


@mcp.tool()
async def subaru_lights_stop(vehicle: VehicleArg = None) -> str:
    """Stop flashing lights via MySubaru lights_stop(). This is a vehicle-control operation. Do not call this unless the user explicitly requested this exact action. Requires MySubaru Security/Companion+. Never pass a VIN, PIN, or password."""
    return await get_session().lights_stop(vehicle)


def run() -> None:
    mcp.run(transport="stdio")
