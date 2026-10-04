"""Button platform for AWTRIX 3 integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import AwtrixClient
from .const import DOMAIN
from .coordinator import AwtrixCoordinator
from .entity import AwtrixEntity


@dataclass(frozen=True, kw_only=True)
class AwtrixButtonDescription(ButtonEntityDescription):
    """Describes an AWTRIX button entity."""

    press_fn: Callable[[AwtrixClient], Coroutine[Any, Any, None]] = (
        lambda client: client.reboot()
    )


BUTTONS: tuple[AwtrixButtonDescription, ...] = (
    AwtrixButtonDescription(
        key="reboot",
        name="Reboot",
        icon="mdi:restart",
        press_fn=lambda client: client.reboot(),
    ),
    AwtrixButtonDescription(
        key="next_app",
        name="Next App",
        icon="mdi:skip-next",
        press_fn=lambda client: client.next_app(),
    ),
    AwtrixButtonDescription(
        key="previous_app",
        name="Previous App",
        icon="mdi:skip-previous",
        press_fn=lambda client: client.previous_app(),
    ),
    AwtrixButtonDescription(
        key="dismiss_notification",
        name="Dismiss Notification",
        icon="mdi:bell-off",
        press_fn=lambda client: client.dismiss_notification(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AWTRIX button entities from a config entry."""
    coordinator: AwtrixCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        AwtrixButton(coordinator, entry, description) for description in BUTTONS
    )


class AwtrixButton(AwtrixEntity, ButtonEntity):
    """Represents an AWTRIX button entity."""

    entity_description: AwtrixButtonDescription

    def __init__(
        self,
        coordinator: AwtrixCoordinator,
        entry: ConfigEntry,
        description: AwtrixButtonDescription,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = (
            f"{entry.unique_id or entry.entry_id}_{description.key}"
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.entity_description.press_fn(self.coordinator.client)
