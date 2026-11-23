"""Binary sensors for Technicolor Homeware."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TechnicolorConfigEntry
from .entity import TechnicolorEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TechnicolorBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor description with a value getter."""

    value_fn: Callable[[dict[str, Any]], bool | None]
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


BINARY_SENSORS: tuple[TechnicolorBinaryDescription, ...] = (
    TechnicolorBinaryDescription(
        key="wan_connected",
        translation_key="wan_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: d["wan"].get("connected"),
        attr_fn=lambda d: {"status": d["wan"].get("status")},
    ),
    TechnicolorBinaryDescription(
        key="broadband",
        translation_key="broadband",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: d["broadband"].get("connected"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TechnicolorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the binary sensors the router actually reports."""
    coordinator = entry.runtime_data
    async_add_entities(
        TechnicolorBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.value_fn(coordinator.data) is not None
    )


class TechnicolorBinarySensor(TechnicolorEntity, BinarySensorEntity):
    """Router binary sensor."""

    entity_description: TechnicolorBinaryDescription

    @property
    def is_on(self) -> bool | None:
        """Current state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Extra attributes."""
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator.data)
