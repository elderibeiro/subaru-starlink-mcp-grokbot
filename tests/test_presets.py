from tests.conftest import FAKE_VIN, FakeController, make_creds
from subaru_mcp.session import SubaruSession


async def test_list_presets(session):
    text = await session.list_climate_presets()
    assert "Full Heat" in text
    assert "Full Cool" in text
    assert FAKE_VIN not in text


async def test_get_preset_sanitized(session):
    text = await session.get_climate_preset("full heat")
    assert "name: Full Heat" in text
    assert "climateZoneFrontTemp: 72" in text
    assert "canEdit" not in text
    assert FAKE_VIN not in text


async def test_get_preset_invalid(session, fake):
    text = await session.get_climate_preset("Hotbox")
    assert text.startswith("[INVALID_PRESET]")
    assert "Full Heat" in text
    assert "Full Cool" in text
    assert fake.remote_start_calls == []


async def test_remote_start_happy_path(session, fake):
    text = await session.remote_start("full heat")
    assert text.startswith("subaru_remote_start: success")
    assert "Full Heat" in text
    assert fake.remote_start_calls == [(FAKE_VIN, "Full Heat")]


async def test_invalid_preset_does_not_call_remote_start(session, fake):
    text = await session.remote_start("Not A Real Preset")
    assert text.startswith("[INVALID_PRESET]")
    assert "remote start was not sent" in text.lower() or "Available:" in text
    assert fake.remote_start_calls == []
    assert "Full Heat" in text
    assert "Full Cool" in text
    assert FAKE_VIN not in text
