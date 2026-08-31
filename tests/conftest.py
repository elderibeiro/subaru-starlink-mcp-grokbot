"""Mock-only fixtures. No live MySubaru network."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
import subarulink.const as sc

from subaru_mcp.secrets import Credentials
from subaru_mcp.session import SubaruSession

FAKE_VIN = "JF2GTADC1MH000001"
FAKE_VIN_2 = "JF2GTADC1MH000002"
FAKE_PASSWORD = "super-secret-pass-xyz"
FAKE_USERNAME = "owner@example.com"
FAKE_PIN = "4242"

PRESETS = [
    {
        "name": "Full Heat",
        "climateZoneFrontTemp": "72",
        "climateZoneFrontTempCelsius": "22",
        "runTimeMinutes": "10",
        "climateZoneFrontAirMode": "AUTO",
        "heatedSeatFrontLeft": "HIGH_HEAT",
        "heatedSeatFrontRight": "HIGH_HEAT",
        "heatedRearWindowActive": "true",
        "climateZoneFrontAirVolume": "AUTO",
        "outerAirCirculation": "outsideAir",
        "airConditionOn": "false",
        "presetType": "subaruPreset",
        "canEdit": "false",
    },
    {
        "name": "Full Cool",
        "climateZoneFrontTemp": "60",
        "climateZoneFrontTempCelsius": "15",
        "runTimeMinutes": "10",
        "climateZoneFrontAirMode": "FACE",
        "heatedSeatFrontLeft": "OFF",
        "heatedSeatFrontRight": "OFF",
        "heatedRearWindowActive": "false",
        "climateZoneFrontAirVolume": "7",
        "outerAirCirculation": "recirculation",
        "airConditionOn": "true",
        "presetType": "subaruPreset",
    },
]


def make_creds(**overrides: Any) -> Credentials:
    data = dict(
        username=FAKE_USERNAME,
        password=FAKE_PASSWORD,
        pin=FAKE_PIN,
        device_id="1756600123456",
        device_name="grok-bot",
        country="USA",
        nickname=None,
    )
    data.update(overrides)
    return Credentials(**data)


class FakeController:
    """In-memory stand-in for subarulink.Controller."""

    device_registered = True

    def __init__(
        self,
        *,
        vehicles: list[dict[str, Any]] | None = None,
        location_valid: bool = True,
        has_tpms: bool = True,
        fail_connect: BaseException | None = None,
        delay: float = 0.0,
    ) -> None:
        self.fail_connect = fail_connect
        self.delay = delay
        self.remote_start_calls: list[tuple[str, str]] = []
        self.lock_calls: list[str] = []
        self.unlock_calls: list[str] = []
        self.horn_calls: list[str] = []
        self.lights_calls: list[str] = []
        self.update_calls: list[str] = []
        self._vehicles = vehicles or [
            {
                "vin": FAKE_VIN,
                "name": "Crosstrek",
                "year": "2021",
                "model": "Crosstrek Sport",
                "tpms": has_tpms,
                "res": True,
                "remote": True,
                "subscription": True,
            }
        ]
        self._presets = {v["vin"]: list(PRESETS) for v in self._vehicles}
        loc_ok = location_valid
        self._data = {
            v["vin"]: {
                sc.VEHICLE_STATUS: {
                    sc.ODOMETER: 45210,
                    sc.DIST_TO_EMPTY: 312,
                    sc.AVG_FUEL_CONSUMPTION: 28.4,
                    sc.VEHICLE_STATE: sc.IGNITION_OFF,
                    sc.TIRE_PRESSURE_FL: 32.1,
                    sc.TIRE_PRESSURE_FR: 32.0,
                    sc.TIRE_PRESSURE_RL: 31.8,
                    sc.TIRE_PRESSURE_RR: 32.2,
                    sc.LOCK_FRONT_LEFT_STATUS: sc.LOCK_LOCKED,
                    sc.LOCK_FRONT_RIGHT_STATUS: sc.LOCK_LOCKED,
                    sc.LOCK_REAR_LEFT_STATUS: sc.LOCK_LOCKED,
                    sc.LOCK_REAR_RIGHT_STATUS: sc.LOCK_LOCKED,
                    sc.LOCK_BOOT_STATUS: sc.LOCK_LOCKED,
                    sc.LATITUDE: 41.85,
                    sc.LONGITUDE: -87.65,
                    sc.LOCATION_VALID: loc_ok,
                },
                sc.VEHICLE_LAST_FETCH: datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
                sc.VEHICLE_LAST_UPDATE: datetime(2026, 8, 30, 10, 0, tzinfo=UTC),
            }
            for v in self._vehicles
        }

    async def connect(self) -> bool:
        if self.fail_connect:
            raise self.fail_connect
        if self.delay:
            await asyncio.sleep(self.delay)
        return True

    def get_vehicles(self) -> list[str]:
        return [v["vin"] for v in self._vehicles]

    def vin_to_name(self, vin: str) -> str:
        return self._find(vin)["name"]

    def get_model_year(self, vin: str) -> str:
        return self._find(vin)["year"]

    def get_model_name(self, vin: str) -> str:
        return self._find(vin)["model"]

    def has_tpms(self, vin: str) -> bool:
        return bool(self._find(vin)["tpms"])

    def get_res_status(self, vin: str) -> bool:
        return bool(self._find(vin)["res"])

    def get_remote_status(self, vin: str) -> bool:
        return bool(self._find(vin)["remote"])

    def get_subscription_status(self, vin: str) -> bool:
        return bool(self._find(vin)["subscription"])

    def _find(self, vin: str) -> dict[str, Any]:
        for item in self._vehicles:
            if item["vin"] == vin:
                return item
        raise KeyError(vin)

    async def get_data(self, vin: str) -> dict[str, Any]:
        if self.delay:
            await asyncio.sleep(self.delay)
        return self._data[vin]

    async def fetch(self, vin: str, force: bool = False) -> bool:
        return True

    async def update(self, vin: str, force: bool = False) -> bool:
        self.update_calls.append(vin)
        return True

    async def list_climate_preset_names(self, vin: str) -> list[str]:
        return [p["name"] for p in self._presets[vin]]

    async def get_climate_preset_by_name(self, vin: str, name: str) -> dict[str, Any] | None:
        for preset in self._presets[vin]:
            if preset["name"] == name:
                return dict(preset)
        return None

    async def lock(self, vin: str) -> bool:
        self.lock_calls.append(vin)
        return True

    async def unlock(self, vin: str, door: str = sc.ALL_DOORS) -> bool:
        self.unlock_calls.append(vin)
        return True

    async def remote_start(self, vin: str, preset_name: str) -> bool:
        self.remote_start_calls.append((vin, preset_name))
        return True

    async def remote_stop(self, vin: str) -> bool:
        return True

    async def horn(self, vin: str) -> bool:
        self.horn_calls.append(vin)
        return True

    async def horn_stop(self, vin: str) -> bool:
        return True

    async def lights(self, vin: str) -> bool:
        self.lights_calls.append(vin)
        return True

    async def lights_stop(self, vin: str) -> bool:
        return True


@pytest.fixture
def fake() -> FakeController:
    return FakeController()


@pytest.fixture
def session(fake: FakeController) -> SubaruSession:
    return SubaruSession(creds=make_creds(), controller=fake, command_timeout=5.0)
