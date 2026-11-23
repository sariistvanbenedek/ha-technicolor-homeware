"""Config flow for Technicolor Homeware."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SSL, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import create_client
from .api import TechnicolorAuthError, TechnicolorError, TechnicolorPageNotFound
from .const import DEFAULT_HOST, DEFAULT_USERNAME, DEVICE_PAGES, DOMAIN, INFO_PAGES
from .parser import extract_info, parse_page

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_HOST)): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, DEFAULT_USERNAME)): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_SSL, default=defaults.get(CONF_SSL, False)): bool,
        }
    )


def _write_files(directory: str, files: dict[str, str]) -> None:
    os.makedirs(directory, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(directory, f"{name}.txt"), "w", encoding="utf-8") as handle:
            handle.write(content)


async def save_login_debug(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Keep the router's public sign-in page and scripts so a login mismatch can be analysed."""
    try:
        client = create_client(hass, data)
        files = await client.async_login_assets()
        directory = hass.config.path("custom_components", DOMAIN, "debug")
        await hass.async_add_executor_job(_write_files, directory, files)
        _LOGGER.warning("Saved the router's sign-in page and scripts to %s", directory)
    except Exception:  # noqa: BLE001 - a troubleshooting aid must never break the flow
        _LOGGER.debug("Could not save the sign-in assets", exc_info=True)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Log in, read the device list and the gateway info."""
    client = create_client(hass, data)
    await client.async_login()
    device_ok = False
    for path in DEVICE_PAGES:
        try:
            await client.async_get(path)
        except TechnicolorPageNotFound:
            continue
        device_ok = True
        break
    if not device_ok:
        raise TechnicolorPageNotFound("device list")
    pages = []
    for path in INFO_PAGES:
        try:
            html = await client.async_get(path)
        except TechnicolorPageNotFound:
            continue
        pages.append(await hass.async_add_executor_job(parse_page, html))
    return extract_info(pages)


class TechnicolorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """First (and only) step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            try:
                info = await validate_input(self.hass, user_input)
            except TechnicolorAuthError as err:
                _LOGGER.warning("Login to %s refused: %s", user_input[CONF_HOST], err)
                errors["base"] = "invalid_auth"
                await save_login_debug(self.hass, user_input)
            except TechnicolorPageNotFound as err:
                _LOGGER.warning("Page missing on %s: %s", user_input[CONF_HOST], err)
                errors["base"] = "unsupported"
            except TechnicolorError as err:
                _LOGGER.warning("Cannot use the web UI at %s: %s", user_input[CONF_HOST], err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"
            else:
                unique = info.get("mac") or info.get("serial") or user_input[CONF_HOST]
                await self.async_set_unique_id(str(unique).lower())
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                model = info.get("product") or "Technicolor"
                return self.async_create_entry(title=f"{model} router", data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=_user_schema(user_input or {}), errors=errors
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The stored password stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                await validate_input(self.hass, data)
            except TechnicolorAuthError:
                errors["base"] = "invalid_auth"
            except TechnicolorError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )
