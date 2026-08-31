
from subarulink.exceptions import RemoteServiceFailure, SubaruException

from subaru_mcp.session import SubaruSession
from tests.conftest import FAKE_PASSWORD, FAKE_VIN, FakeController, make_creds


async def test_lock_success(session, fake):
    text = await session.lock()
    assert text == "subaru_lock: success"
    assert fake.lock_calls == [FAKE_VIN]


async def test_unlock_success(session, fake):
    text = await session.unlock()
    assert text == "subaru_unlock: success"
    assert fake.unlock_calls == [FAKE_VIN]


async def test_lock_false_is_rejected():
    fake = FakeController()

    async def nope(vin):
        return False

    fake.lock = nope
    session = SubaruSession(creds=make_creds(), controller=fake)
    text = await session.lock()
    assert text.startswith("[REJECTED]")
    assert "success" not in text.lower() or "did not succeed" in text


async def test_remote_stop(session):
    text = await session.remote_stop()
    assert text == "subaru_remote_stop: success"


async def test_horn_and_lights(session, fake):
    horn = await session.horn()
    lights = await session.flash_lights()
    assert horn == "subaru_horn: success"
    assert lights == "subaru_flash_lights: success"
    assert fake.horn_calls == [FAKE_VIN]
    assert fake.lights_calls == [FAKE_VIN]


async def test_timeout():
    fake = FakeController(delay=1.0)
    session = SubaruSession(creds=make_creds(), controller=fake, command_timeout=0.05)
    text = await session.lock()
    assert text.startswith("[TIMEOUT]")
    assert FAKE_VIN not in text
    assert FAKE_PASSWORD not in text


async def test_service_failure():
    fake = FakeController()

    async def boom(vin):
        raise SubaruException("HTTP 500 from upstream VIN " + FAKE_VIN)

    fake.lock = boom
    session = SubaruSession(creds=make_creds(), controller=fake)
    text = await session.lock()
    assert text.startswith("[SERVICE_UNAVAILABLE]")
    assert FAKE_VIN not in text


async def test_remote_service_rejected():
    fake = FakeController()

    async def boom(vin):
        raise RemoteServiceFailure("gateway said no for " + FAKE_VIN)

    fake.horn = boom
    session = SubaruSession(creds=make_creds(), controller=fake)
    text = await session.horn()
    assert text.startswith("[REJECTED]")
    assert FAKE_VIN not in text
