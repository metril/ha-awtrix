"""Select platform for AWTRIX 3 integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SETTING_TRANSITION_EFFECT, TRANSITIONS
from .coordinator import AwtrixCoordinator
from .entity import AwtrixEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AWTRIX select entities from a config entry."""
    coordinator: AwtrixCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([AwtrixTransitionSelect(coordinator, entry)])


class AwtrixTransitionSelect(AwtrixEntity, SelectEntity):
    """Select entity for choosing the AWTRIX transition effect."""

    _attr_name = "Transition Effect"
    _attr_icon = "mdi:transition"
    _attr_options = TRANSITIONS

    def __init__(self, coordinator: AwtrixCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_transition_effect"

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        idx = self.coordinator.data.settings.get(SETTING_TRANSITION_EFFECT)
        if idx is None:
            return None
        try:
            return TRANSITIONS[int(idx)]
        except (IndexError, TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        try:
            idx = TRANSITIONS.index(option)
        except ValueError:
            return
        await self.coordinator.client.update_settings({SETTING_TRANSITION_EFFECT: idx})
        if self.coordinator.data is not None:
            self.coordinator.data.settings[SETTING_TRANSITION_EFFECT] = idx
        self.async_write_ha_state()
