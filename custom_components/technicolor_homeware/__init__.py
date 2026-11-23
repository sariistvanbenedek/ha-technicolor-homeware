"""Technicolor Homeware router (e.g. Telekom FGA2235) integration."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import aiohttp

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SSL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import TechnicolorClient
from .const import SWITCH_SPEC_FILE
from .coordinator import TechnicolorConfigEntry, TechnicolorCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
]


def load_switch_specs(path: str | None = None) -> list[dict[str, Any]]:
    """Router settings exposed as switches (see switches.json). Blocking: run in executor."""
    path = path or os.path.join(os.path.dirname(__file__), SWITCH_SPEC_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return []
    except ValueError as err:
        _LOGGER.error("Invalid %s: %s", path, err)
        return []
    specs = []
    for item in raw if isinstance(raw, list) else []:
        if (
            isinstance(item, dict)
            and item.get("key")
            and item.get("name")
            and item.get("page")
            and (item.get("field") or item.get("label"))
            and isinstance(item.get("with_on", {}), dict)
        ):
            specs.append(item)
        else:
            _LOGGER.warning("Ignoring incomplete switch definition: %s", item)
    return specs


def create_client(hass: HomeAssistant, data: dict) -> TechnicolorClient:
    """Client with its own cookie jar (the router is addressed by IP).

    Home Assistant closes the session itself when the config entry unloads.
    """
    session = async_create_clientsession(
        hass,
        verify_ssl=False,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    return TechnicolorClient(
        session,
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data.get(CONF_SSL, False),
        executor=hass.async_add_executor_job,
    )


async def async_setup_entry(hass: HomeAssistant, entry: TechnicolorConfigEntry) -> bool:
    """Set up from a config entry."""
    client = create_client(hass, dict(entry.data))
    specs = await hass.async_add_executor_job(load_switch_specs)
    coordinator = TechnicolorCoordinator(hass, entry, client, specs)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TechnicolorConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
