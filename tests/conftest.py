"""Shared test fixtures for AWTRIX integration tests."""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

pytest_plugins = []


def _make_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def _stub_homeassistant() -> None:
    """Inject minimal homeassistant stubs so our package __init__ can be imported."""
    if "homeassistant" in sys.modules and hasattr(
        sys.modules["homeassistant"], "_full_stub"
    ):
        return  # already done

    # Root package
    ha = _make_module("homeassistant")
    ha._full_stub = True

    # homeassistant.core
    ha_core = _make_module("homeassistant.core", HomeAssistant=MagicMock)
    ha.core = ha_core

    # homeassistant.config_entries
    ha_ce = _make_module("homeassistant.config_entries", ConfigEntry=MagicMock)
    ha.config_entries = ha_ce

    # homeassistant.const
    class _Platform:
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        LIGHT = "light"
        NUMBER = "number"
        SELECT = "select"
        SENSOR = "sensor"
        SWITCH = "switch"

    ha_const = _make_module("homeassistant.const", Platform=_Platform)
    ha.const = ha_const

    # homeassistant.exceptions
    ha_exc = _make_module(
        "homeassistant.exceptions",
        UpdateFailed=Exception,
        HomeAssistantError=Exception,
    )
    ha.exceptions = ha_exc

    # homeassistant.helpers (namespace)
    ha_helpers = _make_module("homeassistant.helpers")
    ha.helpers = ha_helpers

    # homeassistant.helpers.update_coordinator
    from typing import Generic, TypeVar
    _T = TypeVar("_T")

    class _DataUpdateCoordinator(Generic[_T]):
        """Minimal stub for DataUpdateCoordinator."""
        def __init__(self, hass=None, logger=None, *, name="", update_interval=None, **kwargs):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None

        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)

    class _CoordinatorEntity(Generic[_T]):
        """Minimal stub for CoordinatorEntity."""
        def __init__(self, coordinator=None, **kwargs):
            self.coordinator = coordinator

        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)

    ha_uc = _make_module(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=_DataUpdateCoordinator,
        CoordinatorEntity=_CoordinatorEntity,
    )
    ha_helpers.update_coordinator = ha_uc

    # homeassistant.helpers.device_registry
    ha_dr = _make_module(
        "homeassistant.helpers.device_registry",
        DeviceInfo=dict,
    )
    ha_helpers.device_registry = ha_dr

    # homeassistant.helpers.aiohttp_client
    ha_ac = _make_module(
        "homeassistant.helpers.aiohttp_client",
        async_get_clientsession=MagicMock(return_value=MagicMock()),
    )
    ha_helpers.aiohttp_client = ha_ac

    # homeassistant.helpers.entity_registry  (sometimes needed transitively)
    ha_er = _make_module("homeassistant.helpers.entity_registry")
    ha_helpers.entity_registry = ha_er

    # homeassistant.components (for mqtt)
    ha_components = _make_module("homeassistant.components")
    ha_mqtt = _make_module(
        "homeassistant.components.mqtt",
        async_publish=AsyncMock(),
    )
    ha_components.mqtt = ha_mqtt
    ha.components = ha_components

    # Register all modules
    sys.modules.setdefault("homeassistant", ha)
    sys.modules.setdefault("homeassistant.core", ha_core)
    sys.modules.setdefault("homeassistant.config_entries", ha_ce)
    sys.modules.setdefault("homeassistant.const", ha_const)
    sys.modules.setdefault("homeassistant.exceptions", ha_exc)
    sys.modules.setdefault("homeassistant.helpers", ha_helpers)
    sys.modules.setdefault("homeassistant.helpers.update_coordinator", ha_uc)
    sys.modules.setdefault("homeassistant.helpers.device_registry", ha_dr)
    sys.modules.setdefault("homeassistant.helpers.aiohttp_client", ha_ac)
    sys.modules.setdefault("homeassistant.helpers.entity_registry", ha_er)
    sys.modules.setdefault("homeassistant.components", ha_components)
    sys.modules.setdefault("homeassistant.components.mqtt", ha_mqtt)


_stub_homeassistant()
