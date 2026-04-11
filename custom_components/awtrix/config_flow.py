"""Config flow for AWTRIX 3 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlowWithConfigEntry
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .client import AwtrixConnectionError, AwtrixHttpClient
from .const import (
    CONF_APPS,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_MQTT_PREFIX,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONNECTION_HTTP,
    CONNECTION_MQTT,
    DATE_FORMATS,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    TIME_FORMATS,
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


_ALL_APP_NAMES = [
    "weather",
    "temperature",
    "humidity",
    "battery",
    "date",
    "time",
    "countdown",
    "text",
]

_APP_LABELS = {
    "weather": "Weather",
    "temperature": "Temperature",
    "humidity": "Humidity",
    "battery": "Battery",
    "date": "Date",
    "time": "Time",
    "countdown": "Countdown",
    "text": "Text",
}

_WEATHER_MODE_OPTIONS = [
    {"label": "Current conditions", "value": "current"},
    {"label": "Today high/low", "value": "today"},
    {"label": "Hourly forecast", "value": "hourly"},
    {"label": "Daily forecast", "value": "daily"},
]


class AwtrixOptionsFlowHandler(OptionsFlowWithConfigEntry):
    """Two-step options flow: general settings → per-app configuration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__(config_entry)
        self._general_options: dict[str, Any] = {}
        self._enabled_apps: list[str] = []

    # ------------------------------------------------------------------
    # Step 1 — general options + app selection
    # ------------------------------------------------------------------

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        options = self.config_entry.options
        is_http = self.config_entry.data.get(CONF_CONNECTION_TYPE) == CONNECTION_HTTP

        if user_input is not None:
            # Persist poll_interval (HTTP only) and the enabled app list
            self._general_options = {}
            if is_http and CONF_POLL_INTERVAL in user_input:
                self._general_options[CONF_POLL_INTERVAL] = user_input[CONF_POLL_INTERVAL]

            self._enabled_apps = user_input.get("enabled_apps", [])

            if self._enabled_apps:
                return await self.async_step_app_config()

            # No apps selected — save with empty apps dict
            return self.async_create_entry(
                title="",
                data={**self._general_options, CONF_APPS: {}},
            )

        # Build current list of previously-enabled apps for default selection
        existing_apps_cfg: dict = options.get(CONF_APPS, {})
        default_enabled = [
            name for name, cfg in existing_apps_cfg.items() if cfg.get("enabled")
        ]

        schema_dict: dict[vol.Marker, Any] = {}
        if is_http:
            schema_dict[vol.Required(
                CONF_POLL_INTERVAL,
                default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )] = NumberSelector(
                NumberSelectorConfig(min=10, max=300, step=5, unit_of_measurement="seconds")
            )

        schema_dict[vol.Optional("enabled_apps", default=default_enabled)] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"label": _APP_LABELS[name], "value": name}
                    for name in _ALL_APP_NAMES
                ],
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema_dict))

    # ------------------------------------------------------------------
    # Step 2 — per-app configuration
    # ------------------------------------------------------------------

    async def async_step_app_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        options = self.config_entry.options
        existing_apps_cfg: dict = options.get(CONF_APPS, {})

        if user_input is not None:
            apps_cfg: dict[str, Any] = {}
            for name in self._enabled_apps:
                cfg: dict[str, Any] = {"enabled": True}
                if name == "weather":
                    cfg["entity_id"] = user_input.get("weather_entity_id", "")
                    cfg["modes"] = user_input.get("weather_modes", ["current"])
                    cfg["hourly_count"] = int(user_input.get("weather_hourly_count", 4))
                    cfg["daily_count"] = int(user_input.get("weather_daily_count", 5))
                elif name == "temperature":
                    cfg["entity_id"] = user_input.get("temperature_entity_id", "")
                elif name == "humidity":
                    cfg["entity_id"] = user_input.get("humidity_entity_id", "")
                elif name == "battery":
                    cfg["entity_id"] = user_input.get("battery_entity_id", "")
                elif name == "date":
                    cfg["format"] = user_input.get("date_format", next(iter(DATE_FORMATS)))
                elif name == "time":
                    cfg["format"] = user_input.get("time_format", next(iter(TIME_FORMATS)))
                elif name == "countdown":
                    cfg["entity_id"] = user_input.get("countdown_entity_id", "")
                elif name == "text":
                    cfg["entity_id"] = user_input.get("text_entity_id", "")
                apps_cfg[name] = cfg

            return self.async_create_entry(
                title="",
                data={**self._general_options, CONF_APPS: apps_cfg},
            )

        # Build the schema dynamically based on enabled apps
        schema_dict: dict[vol.Marker, Any] = {}

        for name in self._enabled_apps:
            prev = existing_apps_cfg.get(name, {})

            if name == "weather":
                schema_dict[vol.Optional(
                    "weather_entity_id",
                    default=prev.get("entity_id", ""),
                )] = EntitySelector(EntitySelectorConfig(domain="weather"))

                schema_dict[vol.Optional(
                    "weather_modes",
                    default=prev.get("modes", ["current"]),
                )] = SelectSelector(
                    SelectSelectorConfig(
                        options=_WEATHER_MODE_OPTIONS,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )

                schema_dict[vol.Optional(
                    "weather_hourly_count",
                    default=prev.get("hourly_count", 4),
                )] = NumberSelector(NumberSelectorConfig(min=3, max=6, step=1, mode="box"))

                schema_dict[vol.Optional(
                    "weather_daily_count",
                    default=prev.get("daily_count", 5),
                )] = NumberSelector(NumberSelectorConfig(min=3, max=7, step=1, mode="box"))

            elif name == "temperature":
                schema_dict[vol.Optional(
                    "temperature_entity_id",
                    default=prev.get("entity_id", ""),
                )] = EntitySelector(
                    EntitySelectorConfig(domain="sensor", device_class="temperature")
                )

            elif name == "humidity":
                schema_dict[vol.Optional(
                    "humidity_entity_id",
                    default=prev.get("entity_id", ""),
                )] = EntitySelector(
                    EntitySelectorConfig(domain="sensor", device_class="humidity")
                )

            elif name == "battery":
                schema_dict[vol.Optional(
                    "battery_entity_id",
                    default=prev.get("entity_id", ""),
                )] = EntitySelector(
                    EntitySelectorConfig(domain="sensor", device_class="battery")
                )

            elif name == "date":
                schema_dict[vol.Optional(
                    "date_format",
                    default=prev.get("format", next(iter(DATE_FORMATS))),
                )] = SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"label": label, "value": fmt}
                            for fmt, label in DATE_FORMATS.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )

            elif name == "time":
                schema_dict[vol.Optional(
                    "time_format",
                    default=prev.get("format", next(iter(TIME_FORMATS))),
                )] = SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"label": label, "value": fmt}
                            for fmt, label in TIME_FORMATS.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )

            elif name == "countdown":
                schema_dict[vol.Optional(
                    "countdown_entity_id",
                    default=prev.get("entity_id", ""),
                )] = EntitySelector(
                    EntitySelectorConfig(domain=["input_datetime", "timer"])
                )

            elif name == "text":
                schema_dict[vol.Optional(
                    "text_entity_id",
                    default=prev.get("entity_id", ""),
                )] = EntitySelector(
                    EntitySelectorConfig(domain="input_text")
                )

        return self.async_show_form(
            step_id="app_config", data_schema=vol.Schema(schema_dict)
        )
