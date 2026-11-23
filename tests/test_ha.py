"""Home Assistant level tests: config flow, setup, entities, diagnostics, reauth."""

from __future__ import annotations

from aiohttp.test_utils import TestServer
import pytest

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.technicolor_homeware.const import DOMAIN
from custom_components.technicolor_homeware.diagnostics import async_get_config_entry_diagnostics

from .mock_router import MockRouter


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom integrations."""
    return


async def _setup(hass: HomeAssistant, port: int, password: str = "SECRET1234"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": f"127.0.0.1:{port}", "username": "admin", "password": password, "ssl": False},
    )


async def test_full_setup(hass: HomeAssistant, socket_enabled) -> None:
    router = MockRouter()
    async with TestServer(router.app()) as server:
        result = await _setup(hass, server.port)
        assert result["type"] is FlowResultType.CREATE_ENTRY, result
        assert result["title"] == "Telia F1 router"
        await hass.async_block_till_done()
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.state is ConfigEntryState.LOADED
        assert entry.unique_id == "aa:bb:cc:45:18:0e"

        states = {s.entity_id: s for s in hass.states.async_all()}
        print(sorted(states))
        count = next(s for e, s in states.items() if e.endswith("_connected_devices"))
        assert count.state == "1"
        assert count.attributes["devices"][0]["name"] == "EdgeRouter-X"
        wan_ip = next(s for e, s in states.items() if e.endswith("_wan_ip_address"))
        assert wan_ip.state == "77.126.41.183"
        assert any(e.startswith("binary_sensor.") and s.state == "on" for e, s in states.items())
        assert any(e.startswith("button.") and e.endswith("_reboot") for e in states)
        boot = next(s for e, s in states.items() if e.endswith("_last_reboot"))
        assert boot.state not in ("unknown", "unavailable")

        registry = er.async_get(hass)
        trackers = [e for e in er.async_entries_for_config_entry(registry, entry.entry_id) if e.domain == "device_tracker"]
        assert [t.unique_id for t in trackers] == ["74:83:c2:fd:e0:07"]

        # enable the tracker and check presence
        registry.async_update_entity(trackers[0].entity_id, disabled_by=None)
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get(trackers[0].entity_id).state == "home"

        # reboot button
        button = next(e for e in hass.states.async_entity_ids("button") if e.endswith("_reboot"))
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
        assert router.reboots == 1

        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["entry"]["password"] == "**REDACTED**"
        assert "modals/device-modal.lp" in diag["probe"]
        assert "77.126.41.183" not in str(diag)

        # device disappears -> not_home
        router.device_page = "device-modal_len_8.lp"
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(trackers[0].entity_id).state == "not_home"

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_wrong_password(hass: HomeAssistant, socket_enabled) -> None:
    router = MockRouter()
    async with TestServer(router.app()) as server:
        result = await _setup(hass, server.port, password="nope")
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}
        import os
        debug = hass.config.path("custom_components", DOMAIN, "debug")
        assert os.path.exists(os.path.join(debug, "login_page.html.txt"))


async def test_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    result = await _setup(hass, 1)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth(hass: HomeAssistant, socket_enabled) -> None:
    router = MockRouter()
    async with TestServer(router.app()) as server:
        result = await _setup(hass, server.port)
        await hass.async_block_till_done()
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        # password changed on the router
        new = MockRouter(password="NEWPASS99")
        router.verifier = new.verifier
        router.salt = new.salt
        router.expire_sessions()
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        flows = hass.config_entries.flow.async_progress()
        assert flows and flows[0]["context"]["source"] == "reauth"
        result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {"password": "NEWPASS99"})
        assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
        await hass.async_block_till_done()
        assert entry.data["password"] == "NEWPASS99"
        assert entry.state is ConfigEntryState.LOADED
        assert await hass.config_entries.async_unload(entry.entry_id)
