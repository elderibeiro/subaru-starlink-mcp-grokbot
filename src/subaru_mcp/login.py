"""First-run MySubaru 2FA helper. Does not echo passwords or print VINs."""

from __future__ import annotations

import asyncio
import sys

from aiohttp import ClientSession
from subarulink import Controller
from subarulink.exceptions import InvalidCredentials, SubaruException

from subaru_mcp.redact import redact
from subaru_mcp.secrets import load_credentials, missing_pass_keys


def _mask_contact(value: str) -> str:
    if "@" in value:
        local, _, domain = value.partition("@")
        keep = local[:1] if local else ""
        return f"{keep}***@{domain}"
    if len(value) > 4:
        return value[:2] + "***" + value[-2:]
    return "***"


def _read_code() -> str:
    try:
        import stdiomask  # type: ignore

        return str(stdiomask.getpass("Enter 6-digit 2FA code (input hidden): ")).strip()
    except Exception:  # noqa: BLE001
        try:
            import getpass

            return getpass.getpass("Enter 6-digit 2FA code (input hidden): ").strip()
        except Exception:  # noqa: BLE001
            return input("Enter 6-digit 2FA code: ").strip()


async def _login() -> int:
    creds = load_credentials()
    missing = missing_pass_keys(creds)
    if missing:
        print("Credentials are not fully configured. Insert with pass (values are hidden):")
        for key in missing:
            print(f"  pass insert {key}")
        print("Then re-run this script. Do not paste secrets into chat.")
        return 2

    print("Connecting to MySubaru (unofficial reverse-engineered API, USA/Canada).")
    print("This script will not send lock, unlock, or remote-start commands.")
    session = ClientSession()
    try:
        ctrl = Controller(
            session,
            creds.username,
            creds.password,
            int(str(creds.device_id)),
            creds.pin,
            creds.device_name,
            country=creds.country,
        )
        ok = await ctrl.connect()
        if not getattr(ctrl, "device_registered", True):
            methods = dict(ctrl.contact_methods or {})
            if not methods:
                print("Device is not registered and no 2FA contact methods were returned.")
                return 1
            print("This device is not recognized. Choose a 2FA contact method:")
            items = list(methods.items())
            for i, (key, val) in enumerate(items, start=1):
                print(f"  {i}. {key} -> {_mask_contact(str(val))}")
            choice = input("Number: ").strip()
            try:
                idx = int(choice) - 1
                method = items[idx][0]
            except (ValueError, IndexError):
                print("Invalid selection.")
                return 1
            sent = await ctrl.request_auth_code(method)
            if not sent:
                print("Failed to request 2FA code.")
                return 1
            print("A 2FA code was requested. Check that contact method.")
            for attempt in range(3):
                code = _read_code()
                if await ctrl.submit_auth_code(code):
                    print("Device registered. 2FA complete. No VIN is printed.")
                    return 0
                print(f"Verification failed ({attempt + 1}/3).")
            print("Maximum 2FA attempts exceeded.")
            return 1
        if not ok:
            print("Connected but no vehicles were returned. No VIN is printed.")
            return 1
        count = len(ctrl.get_vehicles() or [])
        print(f"Connected. Device already registered. Vehicles on account: {count}.")
        print("2FA not required. No VIN is printed.")
        try:
            for vin in ctrl.get_vehicles() or []:
                name = ctrl.vin_to_name(vin)
                year = ctrl.get_model_year(vin)
                model = ctrl.get_model_name(vin)
                print(f"  - {year} {model} (nickname: {name})")
        except Exception:  # noqa: BLE001
            pass
        return 0
    except InvalidCredentials:
        print("Login failed: MySubaru credentials were rejected.")
        return 1
    except SubaruException as exc:
        print(redact(f"MySubaru error: {exc.message or exc}"))
        return 1
    finally:
        await session.close()


def main() -> None:
    print("Subaru STARLINK MCP first-run helper")
    print("Store secrets with pass, never argv:")
    print("  pass insert subaru/username")
    print("  pass insert subaru/password")
    print("  pass insert subaru/pin")
    print("  pass insert subaru/device-id   # generated automatically if missing")
    print()
    raise SystemExit(asyncio.run(_login()))


if __name__ == "__main__":
    main()
