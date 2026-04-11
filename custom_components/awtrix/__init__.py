"""The AWTRIX 3 integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import AwtrixHttpClient, AwtrixMqttClient
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_MQTT_PREFIX,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONNECTION_HTTP,
    CONNECTION_MQTT,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
)
from .coordinator import AwtrixCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AWTRIX 3 from a config entry."""
    connection_type = entry.data[CONF_CONNECTION_TYPE]

    if connection_type == CONNECTION_HTTP:
        session = async_get_clientsession(hass)
        client = AwtrixHttpClient(
            session=session,
            host=entry.data[CONF_HOST],
            port=entry.data.get(CONF_PORT, DEFAULT_PORT),
            timeout=DEFAULT_HTTP_TIMEOUT,
        )
    else:
        client = AwtrixMqttClient(
            hass=hass,
            prefix=entry.data[CONF_MQTT_PREFIX],
        )

    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    coordinator = AwtrixCoordinator(hass, entry, client, poll_interval=poll_interval)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
