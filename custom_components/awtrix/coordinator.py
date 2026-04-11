"""Data update coordinator for AWTRIX 3 integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import AwtrixClient, AwtrixConnectionError, AwtrixMqttClient
from .const import CONNECTION_MQTT
from .models import AwtrixDeviceData, AwtrixStats

_LOGGER = logging.getLogger(__name__)


class AwtrixCoordinator(DataUpdateCoordinator[AwtrixDeviceData]):
    """Coordinator for AWTRIX3 device data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AwtrixClient,
        poll_interval: int = 30,
        connection_type: str = "http",
    ) -> None:
        self._connection_type = connection_type
        self._unsub_mqtt_stats: Any = None
        self._unsub_mqtt_settings: Any = None

        # MQTT mode: no polling — data arrives via subscription
        interval = None if connection_type == CONNECTION_MQTT else timedelta(seconds=poll_interval)

        super().__init__(
            hass,
            _LOGGER,
            name=f"AWTRIX {entry.title}",
            update_interval=interval,
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self) -> AwtrixDeviceData:
        """Fetch data from the AWTRIX device."""
        if self._connection_type == CONNECTION_MQTT:
            # In MQTT mode we don't poll; return whatever the client has cached.
            assert isinstance(self.client, AwtrixMqttClient)
            stats = await self.client.get_stats()
            settings = await self.client.get_settings()
            return AwtrixDeviceData(
                stats=stats,
                settings=settings,
                effects=[],
                transitions=[],
                connected=stats.uid != "",
            )

        try:
            stats, settings, effects, transitions = await asyncio.gather(
                self.client.get_stats(),
                self.client.get_settings(),
                self.client.get_effects(),
                self.client.get_transitions(),
            )
        except AwtrixConnectionError as err:
            raise UpdateFailed(f"Error communicating with AWTRIX: {err}") from err

        return AwtrixDeviceData(
            stats=stats,
            settings=settings,
            effects=effects,
            transitions=transitions,
            connected=True,
        )

    async def async_start(self) -> None:
        """Subscribe to MQTT topics (MQTT mode only)."""
        if self._connection_type != CONNECTION_MQTT:
            return

        assert isinstance(self.client, AwtrixMqttClient)
        prefix = self.client._prefix

        from homeassistant.components.mqtt import async_subscribe

        self._unsub_mqtt_stats = await async_subscribe(
            self.hass, f"{prefix}/stats", self._handle_mqtt_stats
        )
        self._unsub_mqtt_settings = await async_subscribe(
            self.hass, f"{prefix}/settings", self._handle_mqtt_settings
        )
        _LOGGER.debug("Subscribed to MQTT topics %s/stats and %s/settings", prefix, prefix)

    async def async_stop(self) -> None:
        """Unsubscribe from MQTT topics."""
        for unsub in (self._unsub_mqtt_stats, self._unsub_mqtt_settings):
            if unsub is not None:
                unsub()
        self._unsub_mqtt_stats = None
        self._unsub_mqtt_settings = None

    async def _handle_mqtt_stats(self, message) -> None:
        """Handle an incoming MQTT stats message."""
        assert isinstance(self.client, AwtrixMqttClient)
        try:
            self.client.process_stats_message(message.payload)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Failed to parse MQTT stats message")
            return
        await self._rebuild_data()

    async def _handle_mqtt_settings(self, message) -> None:
        """Handle an incoming MQTT settings message."""
        assert isinstance(self.client, AwtrixMqttClient)
        try:
            self.client.process_settings_message(message.payload)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Failed to parse MQTT settings message")
            return
        await self._rebuild_data()

    async def _rebuild_data(self) -> None:
        """Rebuild device data from the MQTT client's cached state."""
        stats = await self.client.get_stats()
        settings = await self.client.get_settings()
        data = AwtrixDeviceData(
            stats=stats,
            settings=settings,
            effects=self.data.effects if self.data else [],
            transitions=self.data.transitions if self.data else [],
            connected=True,
        )
        self.async_set_updated_data(data)
