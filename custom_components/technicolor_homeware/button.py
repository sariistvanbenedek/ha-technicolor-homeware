"""Reboot button for Technicolor Homeware."""

from __future__ import annotations

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import TechnicolorError
from .coordinator import TechnicolorConfigEntry
from .entity import TechnicolorEntity

PARALLEL_UPDATES = 1

REBOOT = ButtonEntityDescription(
    key="reboot",
    translation_key="reboot",
    device_class=ButtonDeviceClass.RESTART,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TechnicolorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the reboot button only if the web UI offers reboot."""
    coordinator = entry.runtime_data
    if coordinator.data.get("can_reboot"):
        async_add_entities([TechnicolorRebootButton(coordinator, REBOOT)])


class TechnicolorRebootButton(TechnicolorEntity, ButtonEntity):
    """Reboot the router."""

    async def async_press(self) -> None:
        """Send the reboot request."""
        try:
            await self.coordinator.client.async_reboot()
        except TechnicolorError as err:
            raise HomeAssistantError(f"Reboot failed: {err}") from err
