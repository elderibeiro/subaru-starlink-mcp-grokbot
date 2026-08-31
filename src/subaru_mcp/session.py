"""Wrap subarulink.Controller. VIN stays in process memory only."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import subarulink.const as sc
from aiohttp import ClientError, ClientSession
from subarulink import Controller
from subarulink.exceptions import (
    IncompleteCredentials,
    InvalidCredentials,
    InvalidPIN,
    PINLockoutProtect,
    RemoteServiceFailure,
    SubaruException,
    VehicleNotSupported,
)

from subaru_mcp.errors import (
    AUTH_FAILURE,
    AUTH_NOT_CONFIGURED,
    DEVICE_2FA_REQUIRED,
    INVALID_PRESET,
    PIN_INVALID,
    REJECTED,
    SERVICE_UNAVAILABLE,
    STALE_DATA,
    TIMEOUT,
    UNSUPPORTED,
    VEHICLE_UNAVAILABLE,
    error_type_of,
    format_error,
)
from subaru_mcp.redact import redact
from subaru_mcp.secrets import Credentials, load_credentials, missing_pass_keys

LOGGER = logging.getLogger("subaru_mcp")

AUTH_HELP = (
    "MySubaru credentials are not configured. On the box, store them with: "
    "pass insert subaru/username ; pass insert subaru/password ; "
    "pass insert subaru/pin ; then run subaru-mcp-login.sh for device 2FA. "
    "Do not paste secrets into chat."
)

VISIBLE_PRESET_KEYS = (
    "name",
    "climateZoneFrontTemp",
    "climateZoneFrontTempCelsius",
    "runTimeMinutes",
    "climateZoneFrontAirMode",
    "heatedSeatFrontLeft",
    "heatedSeatFrontRight",
    "heatedRearWindowActive",
    "climateZoneFrontAirVolume",
    "outerAirCirculation",
    "airConditionOn",
    "presetType",
)

LOCK_KEYS = (
    sc.LOCK_FRONT_LEFT_STATUS,
    sc.LOCK_FRONT_RIGHT_STATUS,
    sc.LOCK_REAR_LEFT_STATUS,
    sc.LOCK_REAR_RIGHT_STATUS,
    sc.LOCK_BOOT_STATUS,
)

TPMS_KEYS = (
    ("FL", sc.TIRE_PRESSURE_FL),
    ("FR", sc.TIRE_PRESSURE_FR),
    ("RL", sc.TIRE_PRESSURE_RL),
    ("RR", sc.TIRE_PRESSURE_RR),
)


def log_op(op: str, success: bool, duration_ms: float, error_type: str | None = None) -> None:
    parts = [
        f"op={op}",
        f"success={'true' if success else 'false'}",
        f"duration_ms={int(duration_ms)}",
    ]
    if error_type:
        parts.append(f"error_type={error_type}")
    LOGGER.info(redact(" ".join(parts)))


class SubaruSession:
    """One Controller, one aiohttp session. Inject a fake controller in tests."""

    def __init__(
        self,
        *,
        creds: Credentials | None = None,
        controller: Any | None = None,
        command_timeout: float = 90.0,
        websession: ClientSession | None = None,
    ) -> None:
        self._creds = creds
        self._injected_controller = controller
        self._ctrl: Any | None = None
        self._command_timeout = command_timeout
        self._websession = websession
        self._own_websession = False
        self._connected = False
        self._known_vins: set[str] = set()

    def _credentials(self) -> Credentials:
        if self._creds is None:
            self._creds = load_credentials()
        return self._creds

    def _extra_redact(self) -> tuple[str, ...]:
        creds = self._creds
        extras: list[str] = []
        if creds:
            extras.extend(creds.secret_values())
        extras.extend(self._known_vins)
        return tuple(extras)

    def _redact(self, text: str) -> str:
        return redact(text, extra=self._extra_redact())

    def _err(self, error_type: str, message: str) -> str:
        return format_error(error_type, self._redact(message))

    def _format_exc(self, exc: BaseException) -> str:
        raw = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
        msg = self._redact(str(raw))
        if isinstance(exc, (InvalidCredentials, IncompleteCredentials)):
            return self._err(AUTH_FAILURE, "MySubaru login failed.")
        if isinstance(exc, (InvalidPIN, PINLockoutProtect)):
            return self._err(PIN_INVALID, "Vehicle PIN was rejected. Remote commands are blocked to prevent lockout.")
        if isinstance(exc, VehicleNotSupported):
            return self._err(
                UNSUPPORTED,
                msg or "Vehicle or MySubaru Security subscription does not support this command.",
            )
        if isinstance(exc, RemoteServiceFailure):
            return self._err(REJECTED, msg or "MySubaru rejected the remote command.")
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            return self._err(TIMEOUT, "MySubaru request timed out.")
        if isinstance(exc, ClientError):
            return self._err(SERVICE_UNAVAILABLE, "Could not reach MySubaru.")
        if isinstance(exc, SubaruException):
            lowered = msg.lower()
            if "http 5" in lowered or "500" in lowered:
                return self._err(SERVICE_UNAVAILABLE, "MySubaru returned a server error.")
            if "invalid vin" in lowered:
                return self._err(VEHICLE_UNAVAILABLE, "Requested vehicle is not available.")
            return self._err(SERVICE_UNAVAILABLE, msg or "MySubaru request failed.")
        return self._err(SERVICE_UNAVAILABLE, msg or "unexpected error")

    async def aclose(self) -> None:
        if self._own_websession and self._websession is not None and not self._websession.closed:
            await self._websession.close()
        self._websession = None
        self._own_websession = False

    async def _await(self, awaitable: Awaitable[Any]) -> Any:
        return await asyncio.wait_for(awaitable, timeout=self._command_timeout)

    async def _ensure_connected(self) -> str | None:
        creds = self._credentials()
        if not creds.configured():
            keys = ", ".join(missing_pass_keys(creds)) or "subaru/username, subaru/password, subaru/pin"
            return self._err(AUTH_NOT_CONFIGURED, f"{AUTH_HELP} Missing: {keys}.")
        if self._connected and self._ctrl is not None:
            if not getattr(self._ctrl, "device_registered", True):
                return self._err(
                    DEVICE_2FA_REQUIRED,
                    "This device is not registered with MySubaru. Run scripts/subaru-mcp-login.sh once.",
                )
            return None
        if self._injected_controller is not None:
            self._ctrl = self._injected_controller
            ok = await self._await(self._ctrl.connect())
            self._connected = True
            self._remember_vins()
            if not getattr(self._ctrl, "device_registered", True):
                return self._err(
                    DEVICE_2FA_REQUIRED,
                    "This device is not registered with MySubaru. Run scripts/subaru-mcp-login.sh once.",
                )
            if not ok:
                return self._err(VEHICLE_UNAVAILABLE, "MySubaru login succeeded but no vehicles were returned.")
            return None
        try:
            if self._websession is None:
                self._websession = ClientSession()
                self._own_websession = True
            device_id = int(str(creds.device_id))
            self._ctrl = Controller(
                self._websession,
                creds.username,
                creds.password,
                device_id,
                creds.pin,
                creds.device_name,
                country=creds.country,
            )
            ok = await self._await(self._ctrl.connect())
            self._connected = True
            self._remember_vins()
            if not getattr(self._ctrl, "device_registered", True):
                return self._err(
                    DEVICE_2FA_REQUIRED,
                    "This device is not registered with MySubaru. Run scripts/subaru-mcp-login.sh once.",
                )
            if not ok:
                return self._err(VEHICLE_UNAVAILABLE, "MySubaru login succeeded but no vehicles were returned.")
        except (TypeError, ValueError):
            return self._err(AUTH_NOT_CONFIGURED, "subaru/device-id must be an integer.")
        except Exception as exc:  # noqa: BLE001 — mapped to structured errors
            return self._format_exc(exc)
        return None

    def _remember_vins(self) -> None:
        if self._ctrl is None:
            return
        try:
            for vin in self._ctrl.get_vehicles() or []:
                if vin:
                    self._known_vins.add(str(vin).upper())
        except Exception:  # noqa: BLE001
            return

    def _resolve_vin(self, vehicle: str | None) -> tuple[str | None, str | None]:
        """Return (vin, error). VIN is never included in error text."""
        assert self._ctrl is not None
        vins: list[str] = list(self._ctrl.get_vehicles() or [])
        for vin in vins:
            self._known_vins.add(str(vin).upper())
        if not vins:
            return None, self._err(VEHICLE_UNAVAILABLE, "No vehicles on this MySubaru account.")
        nicknames: list[str] = []
        models: list[str] = []
        for vin in vins:
            try:
                nicknames.append(str(self._ctrl.vin_to_name(vin)))
            except Exception:  # noqa: BLE001
                nicknames.append("(unnamed)")
            try:
                year = str(self._ctrl.get_model_year(vin))
                model = str(self._ctrl.get_model_name(vin))
                models.append(f"{year} {model}".strip())
            except Exception:  # noqa: BLE001
                models.append("unknown model")

        if len(vins) == 1:
            return vins[0], None

        wanted = (vehicle or self._credentials().nickname or "").strip().lower()
        if wanted:
            for vin, name in zip(vins, nicknames, strict=True):
                if name.strip().lower() == wanted:
                    return vin, None

        for vin in vins:
            try:
                year = str(self._ctrl.get_model_year(vin))
                model = str(self._ctrl.get_model_name(vin)).lower()
            except Exception:  # noqa: BLE001
                continue
            if year == "2021" and "crosstrek" in model:
                if not wanted:
                    return vin, None

        available = ", ".join(f"{n} ({m})" for n, m in zip(nicknames, models, strict=True)) or "(none)"
        if wanted:
            return None, self._err(
                VEHICLE_UNAVAILABLE,
                f"No vehicle matching nickname {wanted!r}. Available: {available}.",
            )
        return None, self._err(
            VEHICLE_UNAVAILABLE,
            f"Multiple vehicles on this account; pass vehicle=nickname. Available: {available}.",
        )

    async def _execute(self, op: str, fn: Callable[[], Awaitable[str]]) -> str:
        t0 = time.monotonic()
        text = ""
        try:
            text = await fn()
        except Exception as exc:  # noqa: BLE001
            text = self._format_exc(exc)
        duration_ms = (time.monotonic() - t0) * 1000
        err = error_type_of(text)
        log_op(op, success=err is None, duration_ms=duration_ms, error_type=err)
        return self._redact(text)

    async def _require(self, vehicle: str | None) -> tuple[Any, str] | str:
        auth_err = await self._ensure_connected()
        if auth_err:
            return auth_err
        vin, vin_err = self._resolve_vin(vehicle)
        if vin_err:
            return vin_err
        return self._ctrl, vin

    async def status(self, vehicle: str | None = None, *, wake: bool = False) -> str:
        async def _run() -> str:
            got = await self._require(vehicle)
            if isinstance(got, str):
                return got
            ctrl, vin = got
            if wake:
                woke = await self._await(ctrl.update(vin, force=True))
                if not woke:
                    return self._err(
                        REJECTED,
                        "Vehicle wake/update did not succeed. No status refresh was applied.",
                    )
                await self._await(ctrl.fetch(vin, force=True))
            data = await self._await(ctrl.get_data(vin))
            return self._format_status(ctrl, vin, data, woke_vehicle=wake)

        return await self._execute("subaru_refresh_status" if wake else "subaru_status", _run)

    def _format_status(self, ctrl: Any, vin: str, data: dict[str, Any], *, woke_vehicle: bool) -> str:
        vs = data.get(sc.VEHICLE_STATUS) or {}
        nickname = _safe(ctrl.vin_to_name, vin, default="unknown")
        year = _safe(ctrl.get_model_year, vin, default="unknown")
        model = _safe(ctrl.get_model_name, vin, default="unknown")
        sub_ok = _safe(ctrl.get_subscription_status, vin, default=False)
        remote_ok = _safe(ctrl.get_remote_status, vin, default=False)
        res_ok = _safe(ctrl.get_res_status, vin, default=False)
        tpms = _safe(ctrl.has_tpms, vin, default=False)
        last_fetch = data.get(sc.VEHICLE_LAST_FETCH)
        last_update = data.get(sc.VEHICLE_LAST_UPDATE)
        lines = [
            "source: MySubaru telematics (not OBD-II)",
            f"nickname: {nickname}",
            f"model_year: {year}",
            f"model_name: {model}",
            f"lock: {_lock_summary(vs)}",
            f"ignition: {vs.get(sc.VEHICLE_STATE) or 'unknown'}",
            f"fuel_range: {_fmt(vs.get(sc.DIST_TO_EMPTY))}",
            f"odometer: {_fmt(vs.get(sc.ODOMETER))}",
        ]
        if tpms:
            bits = []
            for label, key in TPMS_KEYS:
                bits.append(f"{label}={_fmt(vs.get(key))}")
            lines.append("tpms: " + " ".join(bits))
        else:
            lines.append("tpms: unsupported")
        lines.extend(
            [
                f"subscription_active: {_bool(sub_ok)}",
                f"remote_services: {_bool(remote_ok)}",
                f"remote_engine_start: {_bool(res_ok)}",
                f"last_fetch: {_ts(last_fetch)}",
                f"last_update: {_ts(last_update)}",
                f"woke_vehicle: {_bool(woke_vehicle)}",
            ]
        )
        if woke_vehicle:
            lines.append(
                "note: Vehicle was woken via MySubaru update(); this can drain the 12V battery if overused."
            )
        else:
            lines.append(
                "note: Cached MySubaru server data. subaru_refresh_status wakes the vehicle (12V drain)."
            )
        return "\n".join(lines)

    async def list_climate_presets(self, vehicle: str | None = None) -> str:
        async def _run() -> str:
            got = await self._require(vehicle)
            if isinstance(got, str):
                return got
            ctrl, vin = got
            names = await self._await(ctrl.list_climate_preset_names(vin))
            if not names:
                return "presets: (none)"
            return "presets:\n" + "\n".join(f"- {n}" for n in names)

        return await self._execute("subaru_list_climate_presets", _run)

    async def get_climate_preset(self, name: str, vehicle: str | None = None) -> str:
        async def _run() -> str:
            got = await self._require(vehicle)
            if isinstance(got, str):
                return got
            ctrl, vin = got
            names = list(await self._await(ctrl.list_climate_preset_names(vin)) or [])
            actual = _match_preset(name, names)
            if actual is None:
                listed = ", ".join(names) if names else "(none)"
                return self._err(
                    INVALID_PRESET,
                    f"No climate preset matching {name!r}. Available: {listed}.",
                )
            preset = await self._await(ctrl.get_climate_preset_by_name(vin, actual))
            if not preset:
                listed = ", ".join(names) if names else "(none)"
                return self._err(
                    INVALID_PRESET,
                    f"No climate preset matching {name!r}. Available: {listed}.",
                )
            return _sanitize_preset(preset)

        return await self._execute("subaru_get_climate_preset", _run)

    async def locate(self, vehicle: str | None = None) -> str:
        async def _run() -> str:
            got = await self._require(vehicle)
            if isinstance(got, str):
                return got
            ctrl, vin = got
            woke = await self._await(ctrl.update(vin, force=True))
            if not woke:
                return self._err(REJECTED, "Vehicle wake/update did not succeed. Location not refreshed.")
            await self._await(ctrl.fetch(vin, force=True))
            data = await self._await(ctrl.get_data(vin))
            vs = data.get(sc.VEHICLE_STATUS) or {}
            if vs.get(sc.LOCATION_VALID):
                lat = vs.get(sc.LATITUDE)
                lon = vs.get(sc.LONGITUDE)
                return (
                    "source: MySubaru telematics GPS (not OBD-II)\n"
                    f"location_valid: true\n"
                    f"latitude: {lat}\n"
                    f"longitude: {lon}"
                )
            return self._err(
                STALE_DATA,
                "Live location unavailable (LOCATION_VALID is false after wake). "
                "Coordinates are not reported as current.",
            )

        return await self._execute("subaru_locate", _run)

    async def tire_pressure(self, vehicle: str | None = None) -> str:
        async def _run() -> str:
            got = await self._require(vehicle)
            if isinstance(got, str):
                return got
            ctrl, vin = got
            if not _safe(ctrl.has_tpms, vin, default=False):
                return self._err(UNSUPPORTED, "This vehicle does not report TPMS via MySubaru telematics.")
            data = await self._await(ctrl.get_data(vin))
            vs = data.get(sc.VEHICLE_STATUS) or {}
            lines = ["source: MySubaru telematics (not OBD-II)", "tpms:"]
            for label, key in TPMS_KEYS:
                lines.append(f"  {label}: {_fmt(vs.get(key))}")
            return "\n".join(lines)

        return await self._execute("subaru_tire_pressure", _run)

    async def fuel_status(self, vehicle: str | None = None) -> str:
        async def _run() -> str:
            got = await self._require(vehicle)
            if isinstance(got, str):
                return got
            ctrl, vin = got
            data = await self._await(ctrl.get_data(vin))
            vs = data.get(sc.VEHICLE_STATUS) or {}
            return "\n".join(
                [
                    "source: MySubaru telematics (not OBD-II)",
                    f"fuel_range: {_fmt(vs.get(sc.DIST_TO_EMPTY))}",
                    f"avg_fuel_consumption: {_fmt(vs.get(sc.AVG_FUEL_CONSUMPTION))}",
                    f"remaining_fuel_percent: {_fmt(vs.get(sc.REMAINING_FUEL_PERCENT))}",
                ]
            )

        return await self._execute("subaru_fuel_status", _run)

    async def odometer(self, vehicle: str | None = None) -> str:
        async def _run() -> str:
            got = await self._require(vehicle)
            if isinstance(got, str):
                return got
            ctrl, vin = got
            data = await self._await(ctrl.get_data(vin))
            vs = data.get(sc.VEHICLE_STATUS) or {}
            return "\n".join(
                [
                    "source: MySubaru telematics (not OBD-II)",
                    f"odometer: {_fmt(vs.get(sc.ODOMETER))}",
                ]
            )

        return await self._execute("subaru_odometer", _run)

    async def _command(self, op: str, vehicle: str | None, method_name: str, *args: Any) -> str:
        async def _run() -> str:
            got = await self._require(vehicle)
            if isinstance(got, str):
                return got
            ctrl, vin = got
            method = getattr(ctrl, method_name)
            result = await self._await(method(vin, *args))
            if result is True:
                return f"{op}: success"
            return self._err(REJECTED, f"{op} did not succeed.")

        return await self._execute(op, _run)

    async def lock(self, vehicle: str | None = None) -> str:
        return await self._command("subaru_lock", vehicle, "lock")

    async def unlock(self, vehicle: str | None = None) -> str:
        return await self._command("subaru_unlock", vehicle, "unlock", sc.ALL_DOORS)

    async def remote_stop(self, vehicle: str | None = None) -> str:
        return await self._command("subaru_remote_stop", vehicle, "remote_stop")

    async def horn(self, vehicle: str | None = None) -> str:
        return await self._command("subaru_horn", vehicle, "horn")

    async def horn_stop(self, vehicle: str | None = None) -> str:
        return await self._command("subaru_horn_stop", vehicle, "horn_stop")

    async def flash_lights(self, vehicle: str | None = None) -> str:
        return await self._command("subaru_flash_lights", vehicle, "lights")

    async def lights_stop(self, vehicle: str | None = None) -> str:
        return await self._command("subaru_lights_stop", vehicle, "lights_stop")

    async def remote_start(self, preset_name: str, vehicle: str | None = None) -> str:
        async def _run() -> str:
            got = await self._require(vehicle)
            if isinstance(got, str):
                return got
            ctrl, vin = got
            names = list(await self._await(ctrl.list_climate_preset_names(vin)) or [])
            actual = _match_preset(preset_name, names)
            if actual is None:
                listed = ", ".join(names) if names else "(none)"
                return self._err(
                    INVALID_PRESET,
                    "Preset does not match a MySubaru climate preset; remote start was not sent. "
                    f"Available: {listed}.",
                )
            result = await self._await(ctrl.remote_start(vin, actual))
            if result is True:
                return f"subaru_remote_start: success (preset={actual})"
            return self._err(REJECTED, f"Remote start with preset {actual!r} did not succeed.")

        return await self._execute("subaru_remote_start", _run)


def _match_preset(requested: str, names: list[str]) -> str | None:
    needle = (requested or "").strip().lower()
    if not needle:
        return None
    for name in names:
        if str(name).strip().lower() == needle:
            return str(name)
    return None


def _sanitize_preset(preset: dict[str, Any]) -> str:
    lines = ["source: MySubaru climate preset"]
    for key in VISIBLE_PRESET_KEYS:
        if key in preset:
            lines.append(f"{key}: {preset[key]}")
    if "name" in preset:
        lines.append("note: Crosstrek heated seats cannot be activated remotely; the option is ignored.")
    return "\n".join(lines)


def _lock_summary(vs: dict[str, Any]) -> str:
    vals = []
    for key in LOCK_KEYS:
        val = vs.get(key)
        if val in (None, "", sc.LOCK_UNKNOWN, sc.UNKNOWN):
            continue
        vals.append(val)
    if not vals:
        return "unknown"
    if all(v == sc.LOCK_LOCKED for v in vals):
        return "locked"
    if any(v == sc.LOCK_UNLOCKED for v in vals):
        return "unlocked"
    return "unknown"


def _safe(fn: Callable[..., Any], *args: Any, default: Any) -> Any:
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001
        return default


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "unknown"
    return str(value)


def _bool(value: Any) -> str:
    return "true" if value else "false"


def _ts(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return "unknown"
    return str(value)
