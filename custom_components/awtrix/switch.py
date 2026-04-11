"""Switch platform for AWTRIX 3 integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AwtrixCoordinator
from .entity import AwtrixEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AWTRIX switch entities from a config entry."""
    coordinator: AwtrixCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([AwtrixPowerSwitch(coordinator, entry)])


class AwtrixPowerSwitch(AwtrixEntity, SwitchEntity):
    """Switch to control the power state of the AWTRIX device."""

    _attr_name = "Power"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: AwtrixCoordinator, entry: ConfigEntry) -> None:
        """Initialize the power switch."""
        super().__init__(coordinator, entry)
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_power"
        self._is_on: bool = True

    @property
    def is_on(self) -> bool:
        """Return the current power state."""
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the device on."""
        try:
            await self.coordinator.client.set_power(True)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to turn on AWTRIX device: {err}"
            ) from err
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        try:
            await self.coordinator.client.set_power(False)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to turn off AWTRIX device: {err}"
            ) from err
        self._is_on = False
        self.async_write_ha_state()
