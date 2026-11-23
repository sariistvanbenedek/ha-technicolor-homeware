"""Sensors for Technicolor Homeware."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import TechnicolorConfigEntry
from .entity import TechnicolorEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TechnicolorSensorDescription(SensorEntityDescription):
    """Sensor description with a value getter."""

    value_fn: Callable[[dict[str, Any]], StateType | datetime]
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    always: bool = False


def _connected(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [d for d in data["devices"].values() if d["connected"]]


SENSORS: tuple[TechnicolorSensorDescription, ...] = (
    TechnicolorSensorDescription(
        key="connected_devices",
        translation_key="connected_devices",
        state_class=SensorStateClass.MEASUREMENT,
        always=True,
        value_fn=lambda d: len(_connected(d)),
        attr_fn=lambda d: {
            "devices": [
                {"name": x["name"], "ip": x["ip"], "mac": x["mac"], "interface": x["interface"]}
                for x in sorted(_connected(d), key=lambda x: (x["name"] or x["mac"]).lower())
            ]
        },
    ),
    TechnicolorSensorDescription(
        key="wan_ip",
        translation_key="wan_ip",
        value_fn=lambda d: d["wan"].get("ip"),
    ),
    TechnicolorSensorDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["info"].get("boot_time"),
    ),
    TechnicolorSensorDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["info"].get("cpu"),
    ),
    TechnicolorSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["info"].get("memory"),
    ),
    TechnicolorSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["info"].get("sw_version"),
    ),
    TechnicolorSensorDescription(
        key="line_rate_up",
        translation_key="line_rate_up",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["broadband"].get("up"),
    ),
    TechnicolorSensorDescription(
        key="line_rate_down",
        translation_key="line_rate_down",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["broadband"].get("down"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TechnicolorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the sensors the router actually reports."""
    coordinator = entry.runtime_data
    async_add_entities(
        TechnicolorSensor(coordinator, description)
        for description in SENSORS
        if description.always or description.value_fn(coordinator.data) is not None
    )


class TechnicolorSensor(TechnicolorEntity, SensorEntity):
    """Router sensor."""

    entity_description: TechnicolorSensorDescription

    @property
    def native_value(self) -> StateType | datetime:
        """Current value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Extra attributes."""
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator.data)
