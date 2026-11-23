"""Router settings (Wi-Fi networks, sharing, ...) as switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import TechnicolorError
from .coordinator import TechnicolorConfigEntry, TechnicolorCoordinator
from .entity import TechnicolorEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TechnicolorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One switch per configured setting that the router actually shows."""
    coordinator = entry.runtime_data
    settings = coordinator.data.get("settings", {})
    async_add_entities(
        TechnicolorSettingSwitch(coordinator, spec)
        for spec in coordinator.switch_specs
        if settings.get(spec["key"]) is not None
    )


class TechnicolorSettingSwitch(TechnicolorEntity, SwitchEntity):
    """A switch on one of the router's settings pages."""

    def __init__(self, coordinator: TechnicolorCoordinator, spec: dict[str, Any]) -> None:
        """Initialize."""
        description = SwitchEntityDescription(
            key=f"switch_{spec['key']}",
            name=spec["name"],
            icon=spec.get("icon"),
            entity_category=EntityCategory.CONFIG if spec.get("config", True) else None,
            entity_registry_enabled_default=spec.get("enabled_default", True),
        )
        super().__init__(coordinator, description)
        self._spec = spec
        self._requested: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Current setting (the requested one while the router is saving it)."""
        if self._requested is not None:
            return self._requested
        return self.coordinator.data.get("settings", {}).get(self._spec["key"])

    @property
    def available(self) -> bool:
        """Only while the setting can be read."""
        return super().available and self.is_on is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the setting on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the setting off."""
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        key = self._spec["key"]
        field = self.coordinator.switch_fields.get(key)
        if field is None:
            raise HomeAssistantError(f"{self._spec['name']}: the setting was not found on the router")
        # show the new position at once; a save on the router takes a few seconds
        self._requested = on
        self.async_write_ha_state()
        try:
            await self.coordinator.async_write_setting(self._spec, field, on)
        except TechnicolorError as err:
            raise HomeAssistantError(f"{self._spec['name']}: {err}") from err
        finally:
            # back to what the router reports (the old position if the save failed)
            self._requested = None
            self.async_write_ha_state()
