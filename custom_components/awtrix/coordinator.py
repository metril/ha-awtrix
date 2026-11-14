"""Data update coordinator for AWTRIX 3 integration."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    AwtrixApiError,
    AwtrixClient,
    AwtrixConnectionError,
    AwtrixMqttClient,
)
from .const import CONNECTION_MQTT
from .models import AwtrixDeviceData

_LOGGER = logging.getLogger(__name__)

# MQTT mode: device is considered offline when no stats arrive for this long.
MQTT_STALE_AFTER = timedelta(minutes=3)
MQTT_STALE_CHECK_INTERVAL = timedelta(seconds=60)


class AwtrixCoordinator(DataUpdateCoordinator[AwtrixDeviceData]):
    """Coordinator for AWTRIX3 device data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AwtrixClient,
        poll_interval: int = 30,
        connection_type: str = "http",
        http_client: AwtrixClient | None = None,
    ) -> None:
        self._connection_type = connection_type
        self._http_client = http_client
        self._mqtt_unsubs: list[Any] = []
        self._mqtt_online = True
        self._last_stats_time = time.monotonic()

        # MQTT mode: no polling — data arrives via subscription
        interval = None if connection_type == CONNECTION_MQTT else timedelta(seconds=poll_interval)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"AWTRIX {entry.title}",
            update_interval=interval,
        )
        self.client = client
        self.entry = entry

    @property
    def device_online(self) -> bool:
        """Return True if the device is reachable (poll success or recent MQTT stats)."""
        if self._connection_type == CONNECTION_MQTT:
            return self._mqtt_online
        return self.last_update_success

    @callback
    def _check_mqtt_stale(self, _now=None) -> None:
        """Mark the device offline if no stats message arrived recently."""
        age = time.monotonic() - self._last_stats_time
        if self._mqtt_online and age > MQTT_STALE_AFTER.total_seconds():
            self._mqtt_online = False
            self.async_update_listeners()

    async def _async_update_data(self) -> AwtrixDeviceData:
        """Fetch data from the AWTRIX device."""
        if self._connection_type == CONNECTION_MQTT:
            # If we have an HTTP client, use it for initial data (settings)
            if self._http_client is not None:
                try:
                    stats, settings = await asyncio.gather(
                        self._http_client.get_stats(),
                        self._http_client.get_settings(),
                    )
                    return AwtrixDeviceData(stats=stats, settings=settings, connected=True)
                except Exception:
                    _LOGGER.warning("HTTP initial fetch failed, using MQTT cached data", exc_info=True)

            # Fall back to MQTT cached data
            assert isinstance(self.client, AwtrixMqttClient)
            stats = await self.client.get_stats()
            settings = await self.client.get_settings()
            return AwtrixDeviceData(
                stats=stats,
                settings=settings,
                connected=stats.uid != "",
            )

        try:
            stats, settings = await asyncio.gather(
                self.client.get_stats(),
                self.client.get_settings(),
            )
        except AwtrixApiError as err:
            if err.status == 401:
                raise UpdateFailed(
                    "AWTRIX rejected the credentials (HTTP 401); check username/password"
                ) from err
            raise UpdateFailed(f"AWTRIX API error: {err}") from err
        except (AwtrixConnectionError, ValueError, KeyError, TypeError) as err:
            raise UpdateFailed(f"Error communicating with AWTRIX: {err}") from err

        return AwtrixDeviceData(stats=stats, settings=settings, connected=True)

    async def async_start(self) -> None:
        """Subscribe to MQTT topics (MQTT mode only)."""
        if self._connection_type != CONNECTION_MQTT:
            return

        assert isinstance(self.client, AwtrixMqttClient)
        prefix = self.client.prefix

        from homeassistant.components.mqtt import async_subscribe

        subs = [
            (f"{prefix}/stats", self._handle_mqtt_stats),
            # AWTRIX firmware never publishes to {prefix}/settings — it only
            # listens on that topic for incoming commands.  We keep the
            # subscription for forward-compatibility in case a future firmware
            # adds settings publication.
            (f"{prefix}/settings", self._handle_mqtt_settings),
            (f"{prefix}/stats/currentApp", self._handle_mqtt_current_app),
        ]
        for topic, handler in subs:
            self._mqtt_unsubs.append(await async_subscribe(self.hass, topic, handler))

        self._mqtt_unsubs.append(
            async_track_time_interval(
                self.hass, self._check_mqtt_stale, MQTT_STALE_CHECK_INTERVAL
            )
        )

        _LOGGER.debug("Subscribed to %d MQTT topics for %s", len(subs), prefix)

    async def async_stop(self) -> None:
        """Unsubscribe from MQTT topics."""
        for unsub in self._mqtt_unsubs:
            unsub()
        self._mqtt_unsubs.clear()

    async def _handle_mqtt_stats(self, message) -> None:
        """Handle stats message."""
        assert isinstance(self.client, AwtrixMqttClient)
        try:
            self.client.process_stats_message(message.payload)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Failed to parse MQTT stats message")
            return
        self._last_stats_time = time.monotonic()
        self._mqtt_online = True
        await self._rebuild_data()

    async def _handle_mqtt_settings(self, message) -> None:
        """Handle settings message."""
        assert isinstance(self.client, AwtrixMqttClient)
        try:
            self.client.process_settings_message(message.payload)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Failed to parse MQTT settings message")
            return
        await self._rebuild_data()

    async def _handle_mqtt_current_app(self, message) -> None:
        """Handle currentApp message — plain string, not JSON."""
        if self.data and self.data.stats:
            payload = message.payload
            self.data.stats.current_app = payload if isinstance(payload, str) else payload.decode()
            self.async_set_updated_data(self.data)

    async def _rebuild_data(self) -> None:
        """Rebuild device data from the MQTT client's cached state."""
        stats = await self.client.get_stats()
        mqtt_settings = await self.client.get_settings()
        # Start with existing settings (from HTTP fetch or previous state),
        # then overlay any MQTT-cached settings (from optimistic updates or
        # actual MQTT messages).  AWTRIX firmware does not publish settings
        # via MQTT, so mqtt_settings is typically empty or contains only
        # keys we have optimistically set.
        settings = dict(self.data.settings) if self.data and self.data.settings else {}
        if mqtt_settings:
            settings.update(mqtt_settings)
        data = AwtrixDeviceData(
            stats=stats,
            settings=settings,
            connected=stats.uid != "",
        )
        self.async_set_updated_data(data)
