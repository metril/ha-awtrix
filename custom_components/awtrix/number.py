"""Number platform for AWTRIX 3 integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntityDescription, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SETTING_BRIGHTNESS, SETTING_VOLUME, SETTING_APP_DURATION
from .coordinator import AwtrixCoordinator
from .entity import AwtrixEntity
from .models import AwtrixDeviceData


@dataclass(frozen=True, kw_only=True)
class AwtrixNumberDescription(NumberEntityDescription):
    """Describes an AWTRIX number entity."""

    setting_key: str = ""
    value_fn: Callable[[AwtrixDeviceData, str], Any] = (
        lambda data, key: data.settings.get(key)
    )


NUMBERS: tuple[AwtrixNumberDescription, ...] = (
    AwtrixNumberDescription(
        key="brightness",
        name="Brightness",
        icon="mdi:brightness-6",
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        setting_key=SETTING_BRIGHTNESS,
        value_fn=lambda data, _key: data.stats.brightness,
    ),
    AwtrixNumberDescription(
        key="volume",
        name="Volume",
        icon="mdi:volume-high",
        native_min_value=0,
        native_max_value=30,
        native_step=1,
        setting_key=SETTING_VOLUME,
    ),
    AwtrixNumberDescription(
        key="app_duration",
        name="App Duration",
        icon="mdi:timer-outline",
        native_min_value=1,
        native_max_value=300,
        native_step=1,
        setting_key=SETTING_APP_DURATION,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AWTRIX number entities from a config entry."""
    coordinator: AwtrixCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        AwtrixNumber(coordinator, entry, description) for description in NUMBERS
    )


class AwtrixNumber(AwtrixEntity, NumberEntity):
    """Represents an AWTRIX number entity."""

    entity_description: AwtrixNumberDescription

    def __init__(
        self,
        coordinator: AwtrixCoordinator,
        entry: ConfigEntry,
        description: AwtrixNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = (
            f"{entry.unique_id or entry.entry_id}_{description.key}"
        )

    @property
    def native_value(self) -> float | None:
        """Return the current value from device settings."""
        if self.coordinator.data is None:
            return None
        value = self.entity_description.value_fn(
            self.coordinator.data, self.entity_description.setting_key
        )
        if value is None:
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the setting on the device."""
        try:
            await self.coordinator.client.update_settings(
                {self.entity_description.setting_key: int(value)}
            )
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to set {self.entity_description.key}: {err}"
            ) from err
        # Optimistic update — write to the same field native_value reads
        if self.coordinator.data is not None:
            if self.entity_description.key == "brightness":
                self.coordinator.data.stats.brightness = int(value)
            else:
                self.coordinator.data.settings[self.entity_description.setting_key] = int(value)
        self.async_write_ha_state()
