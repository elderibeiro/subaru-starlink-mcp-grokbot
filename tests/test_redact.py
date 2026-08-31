from subaru_mcp.redact import redact
from subaru_mcp.session import SubaruSession
from tests.conftest import (
    FAKE_PASSWORD,
    FAKE_USERNAME,
    FAKE_VIN,
    FakeController,
    make_creds,
)


def test_redact_patterns():
    blob = f"password={FAKE_PASSWORD} username={FAKE_USERNAME} vin={FAKE_VIN} pin=4242 token=abc.def cookie=xyz"
    out = redact(blob, extra=[FAKE_PASSWORD, FAKE_USERNAME])
    assert FAKE_PASSWORD not in out
    assert FAKE_USERNAME not in out
    assert FAKE_VIN not in out
    assert "4242" not in out
    assert "abc.def" not in out
    assert "vin=***" in out
    assert "[VIN]" in out or "vin=***" in out


def test_redact_vin_in_free_text():
    out = redact(f"gateway error for {FAKE_VIN} please retry")
    assert FAKE_VIN not in out
    assert "[VIN]" in out


async def test_session_output_never_leaks_vin_or_password():
    fake = FakeController()
    session = SubaruSession(creds=make_creds(), controller=fake)
    texts = [
        await session.status(),
        await session.lock(),
        await session.unlock(),
        await session.remote_start("Full Cool"),
        await session.list_climate_presets(),
        await session.locate(),
        await session.horn(),
        await session.flash_lights(),
    ]
    joined = "\n".join(texts)
    assert FAKE_VIN not in joined
    assert FAKE_PASSWORD not in joined
    assert FAKE_USERNAME not in joined


async def test_exception_vin_redacted():
    fake = FakeController()

    async def boom(vin, name):
        raise RuntimeError(f"preset {name} failed VIN={vin} password={FAKE_PASSWORD}")

    fake.remote_start = boom
    session = SubaruSession(creds=make_creds(), controller=fake)
    text = await session.remote_start("Full Heat")
    assert FAKE_VIN not in text
    assert FAKE_PASSWORD not in text
    assert "password=" not in text.lower() or "password=***" in text.lower()
