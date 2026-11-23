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
        assert "modals/device-modal_lp" in diag["probe"]
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



async def test_wifi_switch(hass: HomeAssistant, socket_enabled) -> None:
    from unittest.mock import patch

    from homeassistant.exceptions import HomeAssistantError
    from pytest import raises as _pytest_raises

    specs = [
        {"key": "wifi24", "name": "Wi-Fi 2,4 GHz", "page": "modals/wireless-modal.lp?iface=wl0", "label": "State"},
        {"key": "missing", "name": "Nincs ilyen", "page": "modals/wireless-modal.lp", "label": "Nem létező"},
        {"key": "wrongtab", "name": "Rossz fül", "page": "modals/wireless-modal.lp", "field": "wifi_state",
         "expect_active": "Wireless_Tab_3"},
    ]
    router = MockRouter()
    with patch("custom_components.technicolor_homeware.load_switch_specs", return_value=specs):
        async with TestServer(router.app()) as server:
            await _setup(hass, server.port)
            await hass.async_block_till_done()
            switches = hass.states.async_entity_ids("switch")
            assert len(switches) == 1, switches
            entity_id = switches[0]
            assert hass.states.get(entity_id).state == "on"

            await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
            assert router.wifi["wifi_state"] == "0"
            assert router.wifi["wpa_psk"] == "TOPSECRET123"
            saved = router.saves[-1]
            # default: only the changed field leaves Home Assistant
            assert set(saved) == {"wifi_state", "action", "fromModal", "CSRFtoken"}
            assert hass.states.get(entity_id).state == "off"

            await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
            assert router.wifi["wifi_state"] == "1"
            assert hass.states.get(entity_id).state == "on"

            # a router-side crash is reported, kept for diagnostics, and never leaks what was sent
            router.crash_on_save = True
            with _pytest_raises(HomeAssistantError):
                await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
            entry = hass.config_entries.async_entries(DOMAIN)[0]
            assert entry.runtime_data.client.last_save_report["sent_fields"][0] == "wifi_state"
            with _pytest_raises(Exception):  # full form: the password is sent, but never kept
                await entry.runtime_data.client.async_submit_form(
                    "modals/wireless-modal.lp", "wifi_state", "0", minimal=False
                )
            report = entry.runtime_data.client.last_save_report
            assert report["status"] == 500 and "attempt to concatenate nil" in report["text"]
            assert "TOPSECRET123" not in str(report) and "wpa_psk" in report["sent_fields"]
            diag = await async_get_config_entry_diagnostics(hass, entry)
            assert diag["last_save_error"]["status"] == 500
            router.crash_on_save = False

            # full-form mode: everything else is sent back unchanged
            client = entry.runtime_data.client
            await client.async_submit_form("modals/wireless-modal.lp", "wifi_state", "0", minimal=False)
            saved = router.saves[-1]
            assert saved["ssid"] == "Telekom-301213" and saved["security"] == "wpa2-psk"
            assert saved["wpa_psk"] == "TOPSECRET123" and router.wifi["wifi_state"] == "0"

            # the router refuses a full save: reported, nothing changes
            router.wifi["wpa_psk"] = "CHANGED-ON-ROUTER"
            with _pytest_raises(Exception):
                await client.async_submit_form("modals/wireless-modal.lp", "wifi_state", "1", minimal=False)
            assert router.wifi["wifi_state"] == "0"
            entry = hass.config_entries.async_entries(DOMAIN)[0]
            assert await hass.config_entries.async_unload(entry.entry_id)


async def test_sharing_switches(hass: HomeAssistant, socket_enabled) -> None:
    """DLNA / Samba: full-form save, instant feedback, confirmation, Samba enabled with file sharing."""
    import asyncio
    import time
    from unittest.mock import patch

    from homeassistant.exceptions import HomeAssistantError

    from custom_components.technicolor_homeware import load_switch_specs

    specs = [s for s in load_switch_specs() if s["key"] in ("samba", "dlna")]
    assert len(specs) == 2
    router = MockRouter()
    with patch("custom_components.technicolor_homeware.load_switch_specs", return_value=specs):
        async with TestServer(router.app()) as server:
            await _setup(hass, server.port)
            await hass.async_block_till_done()
            registry = er.async_get(hass)
            ids = {e.unique_id.rsplit("_", 1)[-1]: e.entity_id for e in registry.entities.values()
                   if e.domain == "switch"}
            samba, dlna = ids["samba"], ids["dlna"]
            assert hass.states.get(samba).state == "on"
            assert hass.states.get(dlna).state == "off"
            entry = hass.config_entries.async_entries(DOMAIN)[0]
            coordinator = entry.runtime_data

            # DLNA on: the whole form goes back, nothing else changes
            await hass.services.async_call("switch", "turn_on", {"entity_id": dlna}, blocking=True)
            assert router.sharing["dlnaEnabled"] == "1"
            sent = router.sharing_saves[-1]
            assert sent["usb3Enabled"] == "1" and sent["sambaName"] == "Technicolor"
            assert sent["samba"] == "1" and sent["sambaFilesharing"] == "1"
            assert hass.states.get(dlna).state == "on"
            # confirmed from the save's own answer: no extra page reads, no full refresh
            assert router.requests[-1] == "contentsharing-modal"

            # the switch moves at once, before the router has finished saving
            router.hold_sharing_save = asyncio.Event()
            task = hass.async_create_task(
                hass.services.async_call("switch", "turn_off", {"entity_id": dlna}, blocking=True)
            )
            for _ in range(100):
                await asyncio.sleep(0.02)
                if len(router.sharing_saves) == 2:
                    break
            assert len(router.sharing_saves) == 2
            assert hass.states.get(dlna).state == "off"
            assert router.sharing["dlnaEnabled"] == "1"
            router.hold_sharing_save.set()
            await task
            router.hold_sharing_save = None
            assert router.sharing["dlnaEnabled"] == "0"
            assert hass.states.get(dlna).state == "off"

            # refused by the router: error, and the switch goes back
            router.refuse_sharing = True
            with pytest.raises(HomeAssistantError):
                await hass.services.async_call("switch", "turn_on", {"entity_id": dlna}, blocking=True)
            assert hass.states.get(dlna).state == "off"
            router.refuse_sharing = False

            # Samba turned off on the router itself: file sharing switches it back on too
            router.sharing.update(samba="0", sambaFilesharing="0")
            coordinator.force_settings_refresh()
            await coordinator.async_refresh()
            await hass.async_block_till_done()
            assert hass.states.get(samba).state == "off"
            await hass.services.async_call("switch", "turn_on", {"entity_id": samba}, blocking=True)
            assert router.sharing["samba"] == "1" and router.sharing["sambaFilesharing"] == "1"
            assert router.sharing_saves[-1]["dlnaEnabled"] == "0"
            assert hass.states.get(samba).state == "on"
            # turning it off leaves Samba itself alone
            await hass.services.async_call("switch", "turn_off", {"entity_id": samba}, blocking=True)
            assert router.sharing["samba"] == "1" and router.sharing["sambaFilesharing"] == "0"
            assert hass.states.get(samba).state == "off"

            # a poll that read the page before a save does not undo the save
            page = specs[0]["page"]
            coordinator._written[page] = time.monotonic() + 3600
            router.sharing["sambaFilesharing"] = "1"
            coordinator.force_settings_refresh()
            await coordinator.async_refresh()
            await hass.async_block_till_done()
            assert hass.states.get(samba).state == "off"
            coordinator._written[page] = 0.0
            coordinator.force_settings_refresh()
            await coordinator.async_refresh()
            await hass.async_block_till_done()
            assert hass.states.get(samba).state == "on"

            diag = await async_get_config_entry_diagnostics(hass, entry)
            assert "SHAREPASS77" not in str(diag)
            assert await hass.config_entries.async_unload(entry.entry_id)
