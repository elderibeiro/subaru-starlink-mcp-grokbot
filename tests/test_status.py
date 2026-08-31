from tests.conftest import FAKE_VIN, FAKE_PASSWORD, FakeController, make_creds
from subaru_mcp.session import SubaruSession


async def test_status_compact_no_vin(session):
    text = await session.status()
    assert "MySubaru telematics (not OBD-II)" in text
    assert "nickname: Crosstrek" in text
    assert "model_year: 2021" in text
    assert "lock: locked" in text
    assert "ignition: IGNITION_OFF" in text
    assert "fuel_range: 312" in text
    assert "odometer: 45210" in text
    assert "tpms:" in text
    assert "subscription_active: true" in text
    assert "remote_engine_start: true" in text
    assert FAKE_VIN not in text
    assert FAKE_PASSWORD not in text


async def test_refresh_status_wakes(session, fake):
    text = await session.status(wake=True)
    assert fake.update_calls == [FAKE_VIN]
    assert "woke_vehicle: true" in text
    assert "12V" in text
    assert FAKE_VIN not in text


async def test_odometer_and_fuel(session):
    odo = await session.odometer()
    fuel = await session.fuel_status()
    assert "odometer: 45210" in odo
    assert "fuel_range: 312" in fuel
    assert "avg_fuel_consumption: 28.4" in fuel
    assert FAKE_VIN not in odo + fuel


async def test_tire_pressure(session):
    text = await session.tire_pressure()
    assert "FL: 32.1" in text
    assert FAKE_VIN not in text


async def test_tire_pressure_unsupported():
    fake = FakeController(has_tpms=False)
    session = SubaruSession(creds=make_creds(), controller=fake)
    text = await session.tire_pressure()
    assert text.startswith("[UNSUPPORTED]")
