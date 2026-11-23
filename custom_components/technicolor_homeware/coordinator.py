"""Data update coordinator for Technicolor Homeware."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    TechnicolorAuthError,
    TechnicolorClient,
    TechnicolorError,
    TechnicolorPageNotFound,
)
from .const import (
    DEVICE_PAGES,
    DOMAIN,
    GATEWAY_PAGE,
    HOME_PAGE,
    INFO_PAGES,
    INTERNET_PAGE,
    SCAN_INTERVAL,
    SETTINGS_REFRESH_SECONDS,
    SLOW_REFRESH_SECONDS,
)
from .parser import (
    extract_broadband,
    extract_devices,
    extract_info,
    extract_wan,
    find_switch,
    parse_page,
)

_LOGGER = logging.getLogger(__name__)

type TechnicolorConfigEntry = ConfigEntry[TechnicolorCoordinator]


class TechnicolorCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the router."""

    config_entry: TechnicolorConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TechnicolorConfigEntry,
        client: TechnicolorClient,
        switch_specs: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self._device_page: str | None = None
        self._missing_pages: set[str] = set()
        self._last_slow = 0.0
        self._info: dict[str, Any] = {}
        self._internet: dict[str, Any] | None = None
        self._can_reboot = False
        self._boot_time: datetime | None = None
        self.switch_specs = switch_specs or []
        self.switch_fields: dict[str, str] = {}
        self._settings: dict[str, bool | None] = {}
        self._last_settings = 0.0
        # when each settings page was last written from Home Assistant
        self._written: dict[str, float] = {}

    def force_settings_refresh(self) -> None:
        """Read the settings pages on the next refresh."""
        self._last_settings = 0.0

    async def _refresh_settings(self) -> None:
        pages: dict[str, tuple[float, str | None]] = {}
        for spec in self.switch_specs:
            page = spec["page"]
            if page not in pages:
                started = time.monotonic()
                pages[page] = (started, await self._get_optional(page))
            started, html = pages[page]
            if self._written.get(page, 0.0) >= started:
                # a switch saved this page while it was being read: that answer is newer
                continue
            found = await self.hass.async_add_executor_job(find_switch, html, spec) if html else None
            if found is None:
                self._settings[spec["key"]] = None
                continue
            self.switch_fields[spec["key"]], self._settings[spec["key"]] = found
        self._last_settings = time.monotonic()

    async def _apply_page(self, page: str, html: str) -> dict[str, bool]:
        """Take every switch of `page` from a fresh copy of it."""
        found: dict[str, bool] = {}
        for spec in self.switch_specs:
            if spec["page"] != page:
                continue
            result = await self.hass.async_add_executor_job(find_switch, html, spec)
            if result is not None:
                self.switch_fields[spec["key"]], found[spec["key"]] = result
        self._settings.update(found)
        return found

    async def async_write_setting(self, spec: dict[str, Any], field: str, on: bool) -> None:
        """Save one switch on the router and confirm it from the router's answer.

        Only the page that was saved is read back (often the save's own answer
        already shows it), so the switch settles in a few seconds.
        """
        page = spec["page"]
        started = time.monotonic()
        extra = {name: str(value) for name, value in spec.get("with_on", {}).items()} if on else {}
        answer = await self.client.async_submit_form(
            page,
            field,
            "1" if on else "0",
            tuple(spec.get("omit", ())),
            spec=spec,
            minimal=spec.get("post", "minimal") != "form",
            extra=extra,
        )
        self._written[page] = time.monotonic()
        saved = self._written[page] - started
        state = await self._apply_page(page, answer)
        if state.get(spec["key"]) is not on:
            state = await self._apply_page(page, await self.client.async_get(page))
            self._written[page] = time.monotonic()
        _LOGGER.debug(
            "%s set to %s: saved in %.1f s, confirmed after %.1f s",
            spec["key"],
            on,
            saved,
            time.monotonic() - started,
        )
        if self.data is not None:
            self.async_set_updated_data({**self.data, "settings": dict(self._settings)})
        if state.get(spec["key"]) is not on:
            raise TechnicolorError("the router did not apply the change")

    async def _get_optional(self, path: str) -> str | None:
        if path in self._missing_pages:
            return None
        try:
            return await self.client.async_get(path)
        except TechnicolorPageNotFound:
            self._missing_pages.add(path)
            return None

    async def _parse(self, html: str | None) -> dict[str, Any] | None:
        if html is None:
            return None
        return await self.hass.async_add_executor_job(parse_page, html)

    async def _fetch_devices(self) -> dict[str, dict[str, Any]]:
        candidates = [self._device_page] if self._device_page else list(DEVICE_PAGES)
        for path in candidates:
            html = await self._get_optional(path)
            if html is None:
                continue
            devices = extract_devices(await self._parse(html) or {})
            if devices or self._device_page:
                self._device_page = path
                return devices
        return {}

    async def _slow_refresh(self) -> None:
        pages = []
        for path in INFO_PAGES:
            html = await self._get_optional(path)
            if html is None:
                continue
            if path == GATEWAY_PAGE:
                self._can_reboot = "system_reboot" in html
            if parsed := await self._parse(html):
                pages.append(parsed)
        info = extract_info(pages)
        if any(v is not None for v in info.values()):
            self._info = info
        self._internet = await self._parse(await self._get_optional(INTERNET_PAGE))
        self._last_slow = time.monotonic()

    def _update_boot_time(self, uptime: int | None) -> None:
        if uptime is None:
            return
        boot = (dt_util.utcnow() - timedelta(seconds=uptime)).replace(microsecond=0)
        if self._boot_time is None or abs((boot - self._boot_time).total_seconds()) > 120:
            self._boot_time = boot

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            devices = await self._fetch_devices()
            home = await self._parse(await self._get_optional(HOME_PAGE))
            if not self._last_slow or time.monotonic() - self._last_slow > SLOW_REFRESH_SECONDS:
                await self._slow_refresh()
            if self.switch_specs and (
                not self._last_settings or time.monotonic() - self._last_settings > SETTINGS_REFRESH_SECONDS
            ):
                await self._refresh_settings()
        except TechnicolorAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TechnicolorError as err:
            raise UpdateFailed(str(err)) from err

        info = dict(self._info)
        self._update_boot_time(info.get("uptime_seconds"))
        info["boot_time"] = self._boot_time
        return {
            "devices": devices,
            "info": info,
            "wan": extract_wan(home, self._internet),
            "broadband": extract_broadband(home),
            "can_reboot": self._can_reboot,
            "settings": dict(self._settings),
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Router device."""
        info = (self.data or {}).get("info", {})
        device = DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.unique_id or self.config_entry.entry_id)},
            manufacturer=info.get("vendor") or "Technicolor",
            model=info.get("product") or "Homeware gateway",
            name=self.config_entry.title,
            sw_version=info.get("sw_version"),
            hw_version=info.get("hardware"),
            serial_number=info.get("serial"),
            configuration_url=self.client.base_url,
        )
        if info.get("mac"):
            device["connections"] = {(CONNECTION_NETWORK_MAC, info["mac"])}
        return device
