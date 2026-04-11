"""Config flow for AWTRIX 3 integration."""

from __future__ import annotations

import asyncio
import json
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

MQTT_DISCOVERY_TIMEOUT = 10  # seconds to listen for AWTRIX devices


class AwtrixConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._connection_type: str | None = None
        self._discovered_devices: dict[str, dict] = {}  # prefix -> stats dict

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

    def _discover_from_device_registry(self) -> dict[str, dict]:
        """Find AWTRIX devices already discovered by HA's MQTT integration."""
        from homeassistant.helpers import device_registry as dr, entity_registry as er

        discovered: dict[str, dict] = {}
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)

        for device in dev_reg.devices.values():
            # Look for devices from the mqtt integration with "awtrix" in the name
            is_mqtt_device = any(
                entry_id
                for entry_id in device.config_entries
                if (entry := self.hass.config_entries.async_get_entry(entry_id))
                and entry.domain == "mqtt"
            )
            if not is_mqtt_device:
                continue

            name_lower = (device.name or "").lower()
            if "awtrix" not in name_lower:
                continue

            # Extract the MQTT prefix from entity topics
            # MQTT entities have unique_ids that typically contain the prefix
            prefix = None
            for entity in er.async_entries_for_device(ent_reg, device.id):
                # MQTT entity unique_ids often follow: {prefix}_{component}
                uid = entity.unique_id or ""
                if "awtrix" in uid.lower():
                    # Try to extract prefix: take everything before the last underscore
                    # that looks like an awtrix prefix (e.g., "awtrix_ABCDEF")
                    for identifier in device.identifiers:
                        if isinstance(identifier, tuple) and len(identifier) == 2:
                            _, dev_id = identifier
                            if isinstance(dev_id, str) and "awtrix" in dev_id.lower():
                                prefix = dev_id
                                break
                    if prefix:
                        break

            # Also check connections for mac address to build prefix
            if not prefix:
                for conn_type, conn_id in device.connections:
                    if conn_type == "mac":
                        mac_suffix = conn_id.replace(":", "")[-6:]
                        prefix = f"awtrix_{mac_suffix}"
                        break

            if not prefix:
                # Use device name as fallback
                prefix = name_lower.replace(" ", "_")

            discovered[prefix] = {
                "uid": prefix,
                "ip_address": "",
                "device_name": device.name or prefix,
            }

        return discovered

    async def _discover_from_mqtt_topics(self) -> dict[str, dict]:
        """Subscribe to MQTT and listen for AWTRIX stats messages."""
        from homeassistant.components.mqtt import async_subscribe

        discovered: dict[str, dict] = {}
        event = asyncio.Event()

        def _on_message(message):
            try:
                payload = json.loads(message.payload)
            except (json.JSONDecodeError, TypeError):
                return
            # AWTRIX stats messages contain "uid" and "bat" fields
            if not isinstance(payload, dict) or "uid" not in payload:
                return
            # Extract prefix from topic: "some/prefix/stats" -> "some/prefix"
            topic = message.topic
            if topic.endswith("/stats"):
                prefix = topic[: -len("/stats")]
                discovered[prefix] = payload
                event.set()

        # Use # wildcard to catch any topic depth ending in /stats
        # Filter in callback to only keep AWTRIX stats messages
        unsub = await async_subscribe(self.hass, "#", _on_message)
        try:
            try:
                await asyncio.wait_for(event.wait(), timeout=MQTT_DISCOVERY_TIMEOUT)
                # Found at least one — wait a couple more seconds for others
                await asyncio.sleep(2)
            except TimeoutError:
                pass
        finally:
            unsub()

        return discovered

    async def _discover_mqtt_devices(self) -> dict[str, dict]:
        """Find AWTRIX devices via device registry first, then MQTT subscription."""
        # Method 1: Check if HA already knows about AWTRIX devices via MQTT discovery
        discovered = self._discover_from_device_registry()
        if discovered:
            return discovered

        # Method 2: Listen on MQTT for stats messages
        return await self._discover_from_mqtt_topics()

    async def async_step_mqtt(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        # Check MQTT is configured
        if not self.hass.config_entries.async_entries("mqtt"):
            return self.async_abort(reason="mqtt_not_configured")

        if user_input is not None:
            prefix = user_input[CONF_MQTT_PREFIX]
            # Look up UID from discovery results
            stats = self._discovered_devices.get(prefix, {})
            uid = stats.get("uid", prefix)

            await self.async_set_unique_id(uid)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"AWTRIX ({uid})",
                data={CONF_CONNECTION_TYPE: CONNECTION_MQTT, CONF_MQTT_PREFIX: prefix},
            )

        # Auto-discover AWTRIX devices on MQTT
        self._discovered_devices = await self._discover_mqtt_devices()

        if not self._discovered_devices:
            errors["base"] = "no_devices_found"
            # Fall back to manual entry
            return self.async_show_form(
                step_id="mqtt_manual",
                data_schema=vol.Schema(
                    {vol.Required(CONF_MQTT_PREFIX): TextSelector()}
                ),
                errors=errors,
            )

        # Build selection from discovered devices
        options = []
        for prefix, stats in self._discovered_devices.items():
            uid = stats.get("uid", prefix)
            ip = stats.get("ip_address", "")
            label = f"{uid} ({ip})" if ip else uid
            options.append({"label": label, "value": prefix})

        schema = vol.Schema(
            {
                vol.Required(CONF_MQTT_PREFIX): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="mqtt", data_schema=schema)

    async def async_step_mqtt_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Fallback manual MQTT prefix entry."""
        if user_input is not None:
            prefix = user_input[CONF_MQTT_PREFIX]
            await self.async_set_unique_id(prefix)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"AWTRIX ({prefix})",
                data={CONF_CONNECTION_TYPE: CONNECTION_MQTT, CONF_MQTT_PREFIX: prefix},
            )
        return self.async_show_form(
            step_id="mqtt_manual",
            data_schema=vol.Schema({vol.Required(CONF_MQTT_PREFIX): TextSelector()}),
        )


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
