from tests.conftest import FAKE_VIN, FakeController, make_creds
from subaru_mcp.session import SubaruSession


async def test_locate_valid(session, fake):
    text = await session.locate()
    assert "location_valid: true" in text
    assert "latitude: 41.85" in text
    assert "longitude: -87.65" in text
    assert fake.update_calls == [FAKE_VIN]
    assert FAKE_VIN not in text


async def test_locate_stale():
    fake = FakeController(location_valid=False)
    session = SubaruSession(creds=make_creds(), controller=fake)
    text = await session.locate()
    assert text.startswith("[STALE_DATA]")
    assert "41.85" not in text
    assert FAKE_VIN not in text
