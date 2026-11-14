"""Tests for app manager dedupe/unavailable/forecast, icon listing, night mode."""

from __future__ import annotations

import os
import sys
import types
from datetime import timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from custom_components.awtrix.app_manager import AwtrixAppManager
from custom_components.awtrix.client import AwtrixHttpClient
from custom_components.awtrix.const import SETTING_BRIGHTNESS


def _state(value, **attrs):
    return types.SimpleNamespace(state=value, attributes=attrs)


@pytest.fixture
def manager() -> AwtrixAppManager:
    return AwtrixAppManager(MagicMock(), MagicMock(), {})


def test_unavailable_states_not_pushed(manager):
    for st in ("unavailable", "unknown"):
        assert manager._build_temperature_payload(_state(st), {}) is None
        assert manager._build_humidity_payload(_state(st), {}) is None
        assert manager._build_text_payload(_state(st), {}) is None
        assert manager._build_countdown_payload(_state(st), {}) is None
        assert manager._build_weather_current_payload(_state(st), {}) is None


def test_forecast_hour_uses_local_time(manager):
    local = timezone(timedelta(hours=-5))
    fcs = [{"datetime": "2026-05-20T15:00:00+00:00", "temperature": 20}]
    with patch(
        "custom_components.awtrix.app_manager.dt_util.as_local",
        side_effect=lambda d: d.astimezone(local),
    ):
        p = manager._build_weather_forecast_payload({}, "hourly", fcs)
    assert p["text"].startswith("10A ")  # 15:00 UTC -> 10:00 local


@pytest.mark.asyncio
async def test_identical_payload_not_resent(manager):
    manager._client.send_app = AsyncMock()
    await manager._send_app("x", {"text": "1"})
    await manager._send_app("x", {"text": "1"})
    await manager._send_app("x", {"text": "2"})
    assert manager._client.send_app.await_count == 2
    await manager.async_stop()
    assert manager._last_payloads == {}


@pytest.mark.asyncio
async def test_icons_listed_once():
    session = MagicMock()
    resp = MagicMock(status=200)
    resp.json = AsyncMock(return_value=[{"name": "1.gif"}, {"name": "2.jpg"}])
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=cm)
    client = AwtrixHttpClient(session, "h")
    await client.ensure_icons([1, 2])
    await client.ensure_icons([1, 2])  # cached: no further /list
    assert session.get.call_count == 1


def _import_switch():
    from homeassistant.core import HomeAssistant  # noqa: F401

    def mod(name, **kw):
        m = types.ModuleType(name)
        m.__dict__.update(kw)
        sys.modules.setdefault(name, m)
        return sys.modules[name]

    class _Base:
        _attr_has_entity_name = True

        def __init__(self, coordinator=None, *a, **k):
            self.coordinator = coordinator

        async def async_added_to_hass(self):
            pass

        async def async_get_last_state(self):
            return None

        def async_write_ha_state(self):
            pass

    mod("homeassistant.components.switch", SwitchEntity=type("SwitchEntity", (), {}))
    mod("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    mod("homeassistant.helpers.restore_state", RestoreEntity=type("RestoreEntity", (), {}))
    ent = types.ModuleType("custom_components.awtrix.entity")
    ent.AwtrixEntity = _Base
    coord = types.ModuleType("custom_components.awtrix.coordinator")
    coord.AwtrixCoordinator = MagicMock
    with patch.dict(
        sys.modules,
        {"custom_components.awtrix.entity": ent, "custom_components.awtrix.coordinator": coord},
    ):
        sys.modules.pop("custom_components.awtrix.switch", None)
        import importlib

        return importlib.import_module("custom_components.awtrix.switch")


@pytest.mark.asyncio
async def test_night_mode_double_on_keeps_saved_brightness():
    sw_mod = _import_switch()
    coordinator = MagicMock()
    coordinator.client.update_settings = AsyncMock()
    coordinator.client.switch_app = AsyncMock()
    coordinator.data.settings = {SETTING_BRIGHTNESS: 200}
    entry = MagicMock(options={"night_mode_brightness": 5})
    sw = sw_mod.AwtrixNightModeSwitch(coordinator, entry)
    await sw.async_turn_on()
    coordinator.data.settings[SETTING_BRIGHTNESS] = 5  # device now at night value
    await sw.async_turn_on()
    assert sw._previous_brightness == 200


async def test_resend_after_ttl_or_invalidate(manager):
    from custom_components.awtrix import app_manager as am

    manager._client.send_app = AsyncMock()
    await manager._send_app("a", {"text": "x"})
    await manager._send_app("a", {"text": "x"})
    assert manager._client.send_app.await_count == 1
    manager.invalidate_cache()
    await manager._send_app("a", {"text": "x"})
    assert manager._client.send_app.await_count == 2
    with patch.object(am.time, "monotonic", return_value=1e12):
        await manager._send_app("a", {"text": "x"})
    assert manager._client.send_app.await_count == 3
