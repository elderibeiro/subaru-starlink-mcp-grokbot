from subaru_mcp.server import mcp

REQUIRED = {
    "subaru_status",
    "subaru_refresh_status",
    "subaru_list_climate_presets",
    "subaru_get_climate_preset",
    "subaru_locate",
    "subaru_tire_pressure",
    "subaru_fuel_status",
    "subaru_odometer",
    "subaru_lock",
    "subaru_unlock",
    "subaru_remote_start",
    "subaru_remote_stop",
    "subaru_horn",
    "subaru_flash_lights",
    "subaru_horn_stop",
    "subaru_lights_stop",
}

CONTROL = {
    "subaru_lock",
    "subaru_unlock",
    "subaru_remote_start",
    "subaru_remote_stop",
    "subaru_horn",
    "subaru_flash_lights",
    "subaru_horn_stop",
    "subaru_lights_stop",
}


def test_tool_names_and_safety_text():
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    assert REQUIRED <= set(tools)
    assert "execute" not in tools
    for name, tool in tools.items():
        params = (tool.parameters or {}).get("properties") or {}
        for key in params:
            assert key.lower() not in {"vin", "password", "pin", "token", "cookie", "secret"}
        desc = tool.description or ""
        if name in CONTROL:
            assert "Do not call this unless the user explicitly requested this exact action." in desc
