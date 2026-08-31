from subarulink.exceptions import InvalidCredentials

from subaru_mcp.session import SubaruSession
from tests.conftest import FAKE_PASSWORD, FAKE_USERNAME, FAKE_VIN, FakeController, make_creds


async def test_auth_missing_does_not_raise():
    creds = make_creds(username=None, password=None, pin=None)
    session = SubaruSession(creds=creds, command_timeout=2.0)
    text = await session.status()
    assert text.startswith("[AUTH_NOT_CONFIGURED]")
    assert "pass insert" in text
    assert FAKE_PASSWORD not in text
    assert FAKE_VIN not in text


async def test_auth_configured_status(session):
    text = await session.status()
    assert "Crosstrek" in text
    assert "MySubaru telematics" in text
    assert not text.startswith("[")


async def test_auth_failure_maps():
    fake = FakeController(fail_connect=InvalidCredentials("bad login for " + FAKE_USERNAME))
    session = SubaruSession(creds=make_creds(), controller=fake, command_timeout=2.0)
    text = await session.status()
    assert text.startswith("[AUTH_FAILURE]")
    assert FAKE_USERNAME not in text
    assert FAKE_PASSWORD not in text
    assert "bad login" not in text.lower() or FAKE_USERNAME not in text


async def test_device_2fa_required():
    fake = FakeController()
    fake.device_registered = False
    session = SubaruSession(creds=make_creds(), controller=fake)
    text = await session.status()
    assert text.startswith("[DEVICE_2FA_REQUIRED]")
    assert "subaru-mcp-login.sh" in text
