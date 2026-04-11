"""Config flow for AWTRIX 3 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlowWithConfigEntry
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .client import AwtrixConnectionError, AwtrixHttpClient
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_MQTT_PREFIX,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONNECTION_HTTP,
    CONNECTION_MQTT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_CONNECTION_TYPE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_HTTP): SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"label": "HTTP", "value": CONNECTION_HTTP},
                    {"label": "MQTT", "value": CONNECTION_MQTT},
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)

STEP_HTTP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, step=1, mode="box")
        ),
    }
)

STEP_MQTT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MQTT_PREFIX): TextSelector(),
    }
)


class AwtrixConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._connection_type: str | None = None

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry):
        return AwtrixOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            if self._connection_type == CONNECTION_HTTP:
                return await self.async_step_http()
            return await self.async_step_mqtt()
        return self.async_show_form(step_id="user", data_schema=STEP_CONNECTION_TYPE_SCHEMA)

    async def async_step_http(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            session = async_get_clientsession(self.hass)
            client = AwtrixHttpClient(session=session, host=host, port=port)
            try:
                stats = await client.get_stats()
            except AwtrixConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during AWTRIX connection test")
                errors["base"] = "unknown"
            else:
                uid = stats.uid or f"awtrix_{host}"
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"AWTRIX ({host})",
                    data={CONF_CONNECTION_TYPE: CONNECTION_HTTP, CONF_HOST: host, CONF_PORT: port},
                )
        return self.async_show_form(step_id="http", data_schema=STEP_HTTP_SCHEMA, errors=errors)

    async def async_step_mqtt(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            prefix = user_input[CONF_MQTT_PREFIX]
            if not self.hass.config_entries.async_entries("mqtt"):
                errors["base"] = "mqtt_not_configured"
            else:
                await self.async_set_unique_id(prefix)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"AWTRIX ({prefix})",
                    data={CONF_CONNECTION_TYPE: CONNECTION_MQTT, CONF_MQTT_PREFIX: prefix},
                )
        return self.async_show_form(step_id="mqtt", data_schema=STEP_MQTT_SCHEMA, errors=errors)


class AwtrixOptionsFlowHandler(OptionsFlowWithConfigEntry):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        is_http = self.config_entry.data.get(CONF_CONNECTION_TYPE) == CONNECTION_HTTP
        schema_dict: dict[vol.Marker, Any] = {}
        if is_http:
            schema_dict[vol.Required(
                CONF_POLL_INTERVAL,
                default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )] = NumberSelector(NumberSelectorConfig(min=10, max=300, step=5, unit_of_measurement="seconds"))
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema_dict))
