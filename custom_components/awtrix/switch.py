"""Switch platform for AWTRIX 3 integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_NIGHT_MODE_BRIGHTNESS,
    DOMAIN,
    SETTING_AUTO_BRIGHTNESS,
    SETTING_AUTO_TRANSITION,
    SETTING_BRIGHTNESS,
    SETTING_MATRIX_POWER,
)
from .coordinator import AwtrixCoordinator
from .entity import AwtrixEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AWTRIX switch entities from a config entry."""
    coordinator: AwtrixCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    night_switch = AwtrixNightModeSwitch(coordinator, entry)
    hass.data[DOMAIN][entry.entry_id]["night_mode_switch"] = night_switch
    async_add_entities([
        AwtrixPowerSwitch(coordinator, entry),
        AwtrixAutoBrightnessSwitch(coordinator, entry),
        night_switch,
    ])


class AwtrixPowerSwitch(AwtrixEntity, SwitchEntity):
    """Switch to control the power state of the AWTRIX device."""

    _attr_name = "Power"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: AwtrixCoordinator, entry: ConfigEntry) -> None:
        """Initialize the power switch."""
        super().__init__(coordinator, entry)
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_power"

    @property
    def is_on(self) -> bool | None:
        """Return the current power state."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.settings.get(SETTING_MATRIX_POWER, True)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the device on."""
        try:
            await self.coordinator.client.set_power(True)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to turn on AWTRIX device: {err}"
            ) from err
        if self.coordinator.data is not None:
            self.coordinator.data.settings[SETTING_MATRIX_POWER] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        try:
            await self.coordinator.client.set_power(False)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to turn off AWTRIX device: {err}"
            ) from err
        if self.coordinator.data is not None:
            self.coordinator.data.settings[SETTING_MATRIX_POWER] = False
        self.async_write_ha_state()


class AwtrixAutoBrightnessSwitch(AwtrixEntity, SwitchEntity):
    """Switch to control automatic brightness based on ambient light sensor."""

    _attr_name = "Auto Brightness"
    _attr_icon = "mdi:brightness-auto"

    def __init__(self, coordinator: AwtrixCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_auto_brightness"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.settings.get(SETTING_AUTO_BRIGHTNESS, False)

    async def async_turn_on(self, **kwargs) -> None:
        try:
            await self.coordinator.client.update_settings({SETTING_AUTO_BRIGHTNESS: True})
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to enable auto brightness: {err}"
            ) from err
        if self.coordinator.data:
            self.coordinator.data.settings[SETTING_AUTO_BRIGHTNESS] = True
            self.coordinator.async_set_updated_data(self.coordinator.data)

    async def async_turn_off(self, **kwargs) -> None:
        try:
            await self.coordinator.client.update_settings({SETTING_AUTO_BRIGHTNESS: False})
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to disable auto brightness: {err}"
            ) from err
        if self.coordinator.data:
            self.coordinator.data.settings[SETTING_AUTO_BRIGHTNESS] = False
            self.coordinator.async_set_updated_data(self.coordinator.data)


class AwtrixNightModeSwitch(AwtrixEntity, SwitchEntity):
    """Switch to activate night mode on the AWTRIX device."""

    _attr_name = "Night Mode"
    _attr_icon = "mdi:weather-night"

    def __init__(self, coordinator: AwtrixCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_night_mode"
        self._entry = entry
        self._previous_brightness: int | None = None
        self._is_on: bool = False

    @property
    def is_on(self) -> bool:
        """Return whether night mode is active."""
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        """Activate night mode."""
        # Save current brightness before changing it
        if self.coordinator.data:
            self._previous_brightness = self.coordinator.data.settings.get(SETTING_BRIGHTNESS)

        night_brightness = self._entry.options.get(CONF_NIGHT_MODE_BRIGHTNESS, 0)
        try:
            if night_brightness == 0:
                await self.coordinator.client.update_settings({
                    SETTING_MATRIX_POWER: False,
                    SETTING_AUTO_TRANSITION: False,
                })
            else:
                await self.coordinator.client.update_settings({
                    SETTING_BRIGHTNESS: night_brightness,
                    SETTING_AUTO_TRANSITION: False,
                })
            await self.coordinator.client.switch_app("Time")
        except Exception as err:
            raise HomeAssistantError(f"Failed to activate night mode: {err}") from err
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Deactivate night mode."""
        try:
            await self.coordinator.client.update_settings({
                SETTING_MATRIX_POWER: True,
                SETTING_AUTO_TRANSITION: True,
                SETTING_BRIGHTNESS: self._previous_brightness or 128,
            })
        except Exception as err:
            raise HomeAssistantError(f"Failed to deactivate night mode: {err}") from err
        self._is_on = False
        self.async_write_ha_state()
