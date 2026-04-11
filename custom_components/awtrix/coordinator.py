"""Data update coordinator for AWTRIX 3 integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import UpdateFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import AwtrixClient, AwtrixConnectionError
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
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"AWTRIX {entry.title}",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self) -> AwtrixDeviceData:
        """Fetch data from the AWTRIX device."""
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
