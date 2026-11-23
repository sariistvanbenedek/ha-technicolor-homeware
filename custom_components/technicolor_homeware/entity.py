"""Base entity for Technicolor Homeware."""

from __future__ import annotations

from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import TechnicolorCoordinator


class TechnicolorEntity(CoordinatorEntity[TechnicolorCoordinator]):
    """Entity attached to the router device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TechnicolorCoordinator, description: EntityDescription) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        base = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{base}_{description.key}"
        self._attr_device_info = coordinator.device_info
