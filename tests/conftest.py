"""Shared test fixtures for AWTRIX integration tests."""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

pytest_plugins = []


def _stub_voluptuous() -> None:
    """Inject minimal voluptuous stub so __init__.py can be imported without the package."""
    if "voluptuous" in sys.modules:
        return

    import functools

    vol = types.ModuleType("voluptuous")

    class _Schema:
        def __init__(self, schema, *args, **kwargs):
            self._schema = schema

        def __call__(self, data):
            return data

    class _Required:
        def __init__(self, key, *args, **kwargs):
            self.key = key

        def __hash__(self):
            return hash(self.key)

        def __eq__(self, other):
            if isinstance(other, _Required):
                return self.key == other.key
            return self.key == other

    class _Optional:
        def __init__(self, key, *args, **kwargs):
            self.key = key

        def __hash__(self):
            return hash(self.key)

        def __eq__(self, other):
            if isinstance(other, _Optional):
                return self.key == other.key
            return self.key == other

    def _All(*validators):
        return validators[-1] if validators else lambda x: x

    def _Length(min=None, max=None):
        return lambda x: x

    def _Coerce(tp):
        return tp

    vol.Schema = _Schema
    vol.Required = _Required
    vol.Optional = _Optional
    vol.All = _All
    vol.Length = _Length
    vol.Coerce = _Coerce

    sys.modules["voluptuous"] = vol


_stub_voluptuous()


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
    ha_core = _make_module(
        "homeassistant.core",
        HomeAssistant=MagicMock,
        ServiceCall=MagicMock,
        callback=lambda func: func,  # identity decorator
    )
    ha.core = ha_core

    # homeassistant.config_entries
    class _ConfigEntry:
        def __class_getitem__(cls, item):
            return cls

    class _ConfigEntryState:
        LOADED = "loaded"
        NOT_LOADED = "not_loaded"

    class _ConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            super().__init_subclass__(**kwargs)

    ha_ce = _make_module(
        "homeassistant.config_entries",
        ConfigEntry=_ConfigEntry,
        ConfigEntryState=_ConfigEntryState,
        ConfigFlow=_ConfigFlow,
        ConfigFlowResult=dict,
        OptionsFlowWithReload=type("OptionsFlowWithReload", (), {}),
    )
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

    class _EntityCategory:
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    ha_const = _make_module(
        "homeassistant.const", Platform=_Platform, EntityCategory=_EntityCategory
    )
    ha.const = ha_const

    # homeassistant.exceptions
    ha_exc = _make_module(
        "homeassistant.exceptions",
        UpdateFailed=Exception,
        HomeAssistantError=Exception,
        ServiceValidationError=Exception,
    )
    ha.exceptions = ha_exc

    # homeassistant.helpers (namespace)
    ha_helpers = _make_module("homeassistant.helpers")
    ha.helpers = ha_helpers

    ha_cv = _make_module(
        "homeassistant.helpers.config_validation",
        config_entry_only_config_schema=lambda domain: (lambda config: config),
    )
    ha_helpers.config_validation = ha_cv
    sys.modules.setdefault("homeassistant.helpers.config_validation", ha_cv)

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
        UpdateFailed=Exception,
    )
    ha_helpers.update_coordinator = ha_uc

    # homeassistant.helpers.device_registry
    ha_dr = _make_module(
        "homeassistant.helpers.device_registry",
        DeviceInfo=dict,
    )
    ha_helpers.device_registry = ha_dr

    # homeassistant.helpers.event
    ha_event = _make_module(
        "homeassistant.helpers.event",
        async_track_state_change_event=MagicMock(return_value=lambda: None),
        async_track_time_interval=MagicMock(return_value=lambda: None),
    )
    ha_helpers.event = ha_event

    # homeassistant.helpers.aiohttp_client
    ha_ac = _make_module(
        "homeassistant.helpers.aiohttp_client",
        async_get_clientsession=MagicMock(return_value=MagicMock()),
    )
    ha_helpers.aiohttp_client = ha_ac

    # homeassistant.helpers.entity_registry  (sometimes needed transitively)
    ha_er = _make_module("homeassistant.helpers.entity_registry")
    ha_helpers.entity_registry = ha_er

    # homeassistant.util.dt
    from datetime import datetime, timezone
    ha_util = _make_module("homeassistant.util")
    ha_util_dt = _make_module(
        "homeassistant.util.dt",
        now=lambda: datetime.now(tz=timezone.utc),
    )
    ha_util.dt = ha_util_dt
    ha.util = ha_util

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
    sys.modules.setdefault("homeassistant.helpers.event", ha_event)
    sys.modules.setdefault("homeassistant.helpers.aiohttp_client", ha_ac)
    sys.modules.setdefault("homeassistant.helpers.entity_registry", ha_er)
    sys.modules.setdefault("homeassistant.components", ha_components)
    sys.modules.setdefault("homeassistant.components.mqtt", ha_mqtt)
    sys.modules.setdefault("homeassistant.util", ha_util)
    sys.modules.setdefault("homeassistant.util.dt", ha_util_dt)


_stub_homeassistant()
