"""Light platform for AWTRIX 3 integration."""

from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
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
    """Set up AWTRIX light entities from a config entry."""
    coordinator: AwtrixCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            AwtrixMoodlight(coordinator, entry),
            AwtrixIndicatorLight(coordinator, entry, index=1),
            AwtrixIndicatorLight(coordinator, entry, index=2),
            AwtrixIndicatorLight(coordinator, entry, index=3),
        ]
    )


class AwtrixMoodlight(AwtrixEntity, LightEntity):
    """Light entity to control the AWTRIX moodlight."""

    _attr_name = "Moodlight"
    _attr_icon = "mdi:lightbulb"
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = 1500
    _attr_max_color_temp_kelvin = 10000

    def __init__(self, coordinator: AwtrixCoordinator, entry: ConfigEntry) -> None:
        """Initialize the moodlight."""
        super().__init__(coordinator, entry)
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_moodlight"
        self._color_mode: ColorMode = ColorMode.RGB
        self._is_on: bool = False
        self._brightness: int = 255
        self._rgb_color: tuple[int, int, int] = (255, 255, 255)
        self._color_temp_kelvin: int | None = None

    @property
    def color_mode(self) -> ColorMode:
        """Return the current color mode."""
        return self._color_mode

    @property
    def is_on(self) -> bool:
        """Return whether the moodlight is on."""
        return self._is_on

    @property
    def brightness(self) -> int:
        """Return the current brightness."""
        return self._brightness

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Return the current RGB color."""
        return self._rgb_color

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the current color temperature in Kelvin."""
        return self._color_temp_kelvin

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the moodlight on."""
        brightness = kwargs.get("brightness", self._brightness)
        payload: dict = {"brightness": brightness}

        if "rgb_color" in kwargs:
            self._rgb_color = kwargs["rgb_color"]
            self._color_mode = ColorMode.RGB
            payload["color"] = list(self._rgb_color)
        elif "color_temp_kelvin" in kwargs:
            self._color_temp_kelvin = kwargs["color_temp_kelvin"]
            self._color_mode = ColorMode.COLOR_TEMP
            payload["kelvin"] = self._color_temp_kelvin
        else:
            payload["color"] = list(self._rgb_color)

        try:
            await self.coordinator.client.set_moodlight(payload)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to turn on AWTRIX moodlight: {err}"
            ) from err

        self._brightness = brightness
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the moodlight off by sending empty payload."""
        try:
            await self.coordinator.client.set_moodlight(None)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to turn off AWTRIX moodlight: {err}"
            ) from err

        self._is_on = False
        self.async_write_ha_state()


class AwtrixIndicatorLight(AwtrixEntity, LightEntity):
    """Light entity to control an AWTRIX indicator LED."""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}

    def __init__(
        self, coordinator: AwtrixCoordinator, entry: ConfigEntry, index: int
    ) -> None:
        """Initialize the indicator light."""
        super().__init__(coordinator, entry)
        self._index = index
        self._attr_name = f"Indicator {index}"
        self._attr_icon = "mdi:led-on"
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_indicator_{index}"
        self._is_on: bool = False
        self._rgb_color: tuple[int, int, int] = (255, 255, 255)

    @property
    def is_on(self) -> bool:
        """Return whether the indicator is on."""
        return self._is_on

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Return the current RGB color."""
        return self._rgb_color

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the indicator light on."""
        if "rgb_color" in kwargs:
            self._rgb_color = kwargs["rgb_color"]

        try:
            await self.coordinator.client.set_indicator(
                self._index, list(self._rgb_color)
            )
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to turn on AWTRIX indicator {self._index}: {err}"
            ) from err

        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the indicator light off."""
        try:
            await self.coordinator.client.set_indicator(self._index, None)
        except Exception as err:
            raise HomeAssistantError(
                f"Failed to turn off AWTRIX indicator {self._index}: {err}"
            ) from err

        self._is_on = False
        self.async_write_ha_state()
