"""Presence detection from the router's device list."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import TechnicolorConfigEntry, TechnicolorCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TechnicolorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Track every device the router has seen (restoring earlier ones)."""
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    known: dict[str, str | None] = {
        reg.unique_id: reg.original_name
        for reg in er.async_entries_for_config_entry(registry, entry.entry_id)
        if reg.domain == DEVICE_TRACKER_DOMAIN
    }
    tracked: set[str] = set()

    @callback
    def _add_new(initial: bool = False) -> None:
        macs = set(coordinator.data["devices"])
        if initial:
            macs |= set(known)
        new = macs - tracked
        if not new:
            return
        tracked.update(new)
        async_add_entities(TechnicolorTracker(coordinator, mac, known.get(mac)) for mac in sorted(new))

    _add_new(initial=True)
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class TechnicolorTracker(CoordinatorEntity[TechnicolorCoordinator], ScannerEntity):
    """A device seen on the router's LAN / Wi-Fi."""

    def __init__(self, coordinator: TechnicolorCoordinator, mac: str, last_name: str | None) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._mac = mac
        self._last_name = last_name
        self._attr_unique_id = mac
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, mac)}, default_name=last_name or mac
        )

    @property
    def _device(self) -> dict[str, Any] | None:
        return self.coordinator.data["devices"].get(self._mac)

    @property
    def name(self) -> str:
        """Hostname as reported by the router."""
        device = self._device
        if device and device["name"]:
            self._last_name = device["name"]
        return self._last_name or self._mac

    @property
    def source_type(self) -> SourceType:
        """Router based tracking."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Device is on the network."""
        device = self._device
        return bool(device and device["connected"])

    @property
    def mac_address(self) -> str:
        """MAC address."""
        return self._mac

    @property
    def ip_address(self) -> str | None:
        """IPv4 address."""
        device = self._device
        return device["ip"] if device else None

    @property
    def hostname(self) -> str | None:
        """Hostname."""
        device = self._device
        return (device["name"] or None) if device else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Connection details."""
        device = self._device
        return {"interface": device["interface"]} if device and device.get("interface") else {}
