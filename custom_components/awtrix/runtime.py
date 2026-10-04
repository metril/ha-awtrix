"""Runtime data for the AWTRIX 3 integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from homeassistant.config_entries import ConfigEntry

from .coordinator import AwtrixCoordinator


@dataclass
class AwtrixRuntimeData:
    """Objects shared between the integration and its platforms."""

    coordinator: AwtrixCoordinator
    client: Any
    icon_client: Any = None
    app_manager: Any = None
    night_mode_switch: Any = None
    unsub_listeners: list[Callable[[], None]] = field(default_factory=list)


AwtrixConfigEntry: TypeAlias = ConfigEntry[AwtrixRuntimeData]
