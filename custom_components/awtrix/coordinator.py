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
        http_client: AwtrixClient | None = None,
    ) -> None:
        self._connection_type = connection_type
        self._http_client = http_client
        self._mqtt_unsubs: list[Any] = []

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

    async def _async_update_data(self) -> AwtrixDeviceData:
        """Fetch data from the AWTRIX device."""
        if self._connection_type == CONNECTION_MQTT:
            # If we have an HTTP client, use it for initial data (settings, effects, transitions)
            if self._http_client is not None:
                try:
                    stats, settings, effects, transitions = await asyncio.gather(
                        self._http_client.get_stats(),
                        self._http_client.get_settings(),
                        self._http_client.get_effects(),
                        self._http_client.get_transitions(),
                    )
                    return AwtrixDeviceData(
                        stats=stats,
                        settings=settings,
                        effects=effects,
                        transitions=transitions,
                        connected=True,
                    )
                except Exception:
                    _LOGGER.warning("HTTP initial fetch failed, using MQTT cached data", exc_info=True)

            # Fall back to MQTT cached data
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

        subs = [
            (f"{prefix}/stats", self._handle_mqtt_stats),
            # AWTRIX firmware never publishes to {prefix}/settings — it only
            # listens on that topic for incoming commands.  We keep the
            # subscription for forward-compatibility in case a future firmware
            # adds settings publication.
            (f"{prefix}/settings", self._handle_mqtt_settings),
            (f"{prefix}/stats/currentApp", self._handle_mqtt_current_app),
            (f"{prefix}/stats/effects", self._handle_mqtt_effects),
            (f"{prefix}/stats/transitions", self._handle_mqtt_transitions),
        ]
        for topic, handler in subs:
            self._mqtt_unsubs.append(await async_subscribe(self.hass, topic, handler))

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

    async def _handle_mqtt_effects(self, message) -> None:
        """Handle effects list message."""
        import json
        try:
            effects = json.loads(message.payload)
            if self.data and isinstance(effects, list):
                self.data.effects = effects
                self.async_set_updated_data(self.data)
        except (json.JSONDecodeError, TypeError):
            pass

    async def _handle_mqtt_transitions(self, message) -> None:
        """Handle transitions list message."""
        import json
        try:
            transitions = json.loads(message.payload)
            if self.data and isinstance(transitions, list):
                self.data.transitions = transitions
                self.async_set_updated_data(self.data)
        except (json.JSONDecodeError, TypeError):
            pass

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
            effects=self.data.effects if self.data else [],
            transitions=self.data.transitions if self.data else [],
            connected=stats.uid != "",
        )
        self.async_set_updated_data(data)
