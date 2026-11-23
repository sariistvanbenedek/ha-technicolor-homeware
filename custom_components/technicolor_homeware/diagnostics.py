"""Diagnostics: current data plus a read-only survey of the router's web UI."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .api import TechnicolorError
from .coordinator import TechnicolorConfigEntry
from .parser import mask

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "serial"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TechnicolorConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = dict(coordinator.data or {})
    if isinstance(data.get("info"), dict):
        data["info"] = {k: (str(v) if k == "boot_time" and v else v) for k, v in data["info"].items()}
    try:
        probe: Any = {
            # dots in page names make the keys hard to address in tools
            path.replace(".", "_"): page
            for path, page in (await coordinator.client.async_probe()).items()
        }
    except TechnicolorError as err:
        probe = {"error": str(err)}
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "data": mask(async_redact_data(data, TO_REDACT)),
        "last_save_error": coordinator.client.last_save_report,
        "probe": probe,
    }
