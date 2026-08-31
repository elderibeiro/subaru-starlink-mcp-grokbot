from subarulink.exceptions import InvalidPIN, VehicleNotSupported

from subaru_mcp.errors import error_type_of, format_error
from subaru_mcp.session import SubaruSession
from tests.conftest import FAKE_VIN, FakeController, make_creds


def test_format_error():
    text = format_error("INVALID_PRESET", "nope")
    assert text == "[INVALID_PRESET] nope"
    assert error_type_of(text) == "INVALID_PRESET"
    assert error_type_of("ok") is None


async def test_pin_invalid():
    fake = FakeController()

    async def boom(vin):
        raise InvalidPIN("Invalid PIN! " + FAKE_VIN)

    fake.lock = boom
    session = SubaruSession(creds=make_creds(), controller=fake)
    text = await session.lock()
    assert text.startswith("[PIN_INVALID]")
    assert FAKE_VIN not in text


async def test_unsupported():
    fake = FakeController()

    async def boom(vin, name):
        raise VehicleNotSupported("Active MySubaru Security Plus subscription required.")

    fake.remote_start = boom
    session = SubaruSession(creds=make_creds(), controller=fake)
    text = await session.remote_start("Full Heat")
    assert text.startswith("[UNSUPPORTED]")
