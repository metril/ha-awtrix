"""Tests for the AWTRIX MQTT client."""

from __future__ import annotations

import sys
import os

# Allow importing the custom component without Home Assistant installed.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub out homeassistant modules before any imports that may trigger them.
import types
from unittest.mock import AsyncMock, MagicMock

_mqtt_module = types.ModuleType("homeassistant.components.mqtt")
_mqtt_module.async_publish = AsyncMock()  # placeholder; tests will replace this
_components_module = types.ModuleType("homeassistant.components")
_components_module.mqtt = _mqtt_module
_ha_module = types.ModuleType("homeassistant")
_ha_module.components = _components_module
sys.modules.setdefault("homeassistant", _ha_module)
sys.modules.setdefault("homeassistant.components", _components_module)
sys.modules.setdefault("homeassistant.components.mqtt", _mqtt_module)

import json
from unittest.mock import patch

import pytest

from custom_components.awtrix.client import AwtrixMqttClient
from custom_components.awtrix.models import AwtrixStats

PREFIX = "awtrix/device1"


def _make_client():
    """Return an AwtrixMqttClient with a mock hass."""
    hass = MagicMock()
    return AwtrixMqttClient(hass, PREFIX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_mqtt():
    """Context manager that patches homeassistant.components.mqtt.async_publish."""
    return patch("homeassistant.components.mqtt.async_publish", new_callable=AsyncMock)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_power():
    """set_power() should publish to {prefix}/power with the power flag."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.set_power(True)

    mock_publish.assert_awaited_once()
    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/power"
    assert json.loads(payload) == {"power": True}


@pytest.mark.asyncio
async def test_set_power_off():
    """set_power(False) should publish power=False."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.set_power(False)

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/power"
    assert json.loads(payload) == {"power": False}


@pytest.mark.asyncio
async def test_send_notification():
    """send_notification() should publish to {prefix}/notify."""
    client = _make_client()
    notif = {"text": "Hello!", "color": "#FF0000"}
    with _patch_mqtt() as mock_publish:
        await client.send_notification(notif)

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/notify"
    assert json.loads(payload) == notif


@pytest.mark.asyncio
async def test_send_app():
    """send_app() should publish to {prefix}/custom/{name}."""
    client = _make_client()
    app_payload = {"text": "Sunny", "icon": "2283"}
    with _patch_mqtt() as mock_publish:
        await client.send_app("weather", app_payload)

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/custom/weather"
    assert json.loads(payload) == app_payload


@pytest.mark.asyncio
async def test_remove_app():
    """remove_app() should publish an empty dict to {prefix}/custom/{name}."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.remove_app("weather")

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/custom/weather"
    assert json.loads(payload) == {}


@pytest.mark.asyncio
async def test_set_indicator():
    """set_indicator() should publish colour to {prefix}/indicator{n}."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.set_indicator(2, [0, 255, 0])

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/indicator2"
    assert json.loads(payload) == {"color": [0, 255, 0]}


@pytest.mark.asyncio
async def test_set_indicator_clear():
    """set_indicator() with None should publish an empty dict."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.set_indicator(1, None)

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/indicator1"
    assert json.loads(payload) == {}


@pytest.mark.asyncio
async def test_reboot():
    """reboot() should publish an empty string to {prefix}/reboot."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.reboot()

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/reboot"
    assert payload == ""


@pytest.mark.asyncio
async def test_process_stats_message():
    """process_stats_message() should parse JSON into AwtrixStats."""
    client = _make_client()
    stats_data = {
        "uid": "AABB",
        "bat": 90,
        "bat_raw": 750,
        "lux": 200,
        "ldr_raw": 400,
        "ram": 120000,
        "bri": 100,
        "temp": 21.0,
        "hum": 50.0,
        "uptime": 7200,
        "wifi_signal": -60,
        "version": "0.99",
        "ip_address": "192.168.1.99",
        "currentApp": "weather",
    }
    client.process_stats_message(json.dumps(stats_data))

    assert client.last_stats is not None
    assert isinstance(client.last_stats, AwtrixStats)
    assert client.last_stats.uid == "AABB"
    assert client.last_stats.battery == 90
    assert client.last_stats.temperature == 21.0
    assert client.last_stats.firmware == "0.99"
    assert client.last_stats.current_app == "weather"


@pytest.mark.asyncio
async def test_process_settings_message():
    """process_settings_message() should parse JSON into _last_settings."""
    client = _make_client()
    settings = {"BRI": 128, "MATP": True}
    client.process_settings_message(json.dumps(settings))

    assert client._last_settings == settings


@pytest.mark.asyncio
async def test_get_stats_empty_before_message():
    """get_stats() should return an empty AwtrixStats before any message is received."""
    client = _make_client()
    result = await client.get_stats()
    assert isinstance(result, AwtrixStats)
    assert result.uid == ""


@pytest.mark.asyncio
async def test_get_settings_empty_before_message():
    """get_settings() should return {} before any message is received."""
    client = _make_client()
    result = await client.get_settings()
    assert result == {}


@pytest.mark.asyncio
async def test_get_effects_returns_empty_list():
    """get_effects() is not available via MQTT and should return []."""
    client = _make_client()
    assert await client.get_effects() == []


@pytest.mark.asyncio
async def test_get_transitions_returns_empty_list():
    """get_transitions() is not available via MQTT and should return []."""
    client = _make_client()
    assert await client.get_transitions() == []


@pytest.mark.asyncio
async def test_get_screen_returns_empty_bytes():
    """get_screen() is not available via MQTT and should return b''."""
    client = _make_client()
    assert await client.get_screen() == b""


@pytest.mark.asyncio
async def test_dismiss_notification():
    """dismiss_notification() should publish to {prefix}/notify/dismiss."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.dismiss_notification()

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/notify/dismiss"
    assert payload == ""


@pytest.mark.asyncio
async def test_play_sound():
    """play_sound() should publish to {prefix}/sound."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.play_sound("chime")

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/sound"
    assert json.loads(payload) == {"sound": "chime"}


@pytest.mark.asyncio
async def test_play_rtttl():
    """play_rtttl() should publish the melody string directly to {prefix}/rtttl."""
    client = _make_client()
    melody = "Tetris:d=4,o=5,b=160:e6"
    with _patch_mqtt() as mock_publish:
        await client.play_rtttl(melody)

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/rtttl"
    assert payload == melody


@pytest.mark.asyncio
async def test_switch_app():
    """switch_app() should publish to {prefix}/switch."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.switch_app("clock")

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/switch"
    assert json.loads(payload) == {"name": "clock"}


@pytest.mark.asyncio
async def test_sleep():
    """sleep() should publish to {prefix}/sleep."""
    client = _make_client()
    with _patch_mqtt() as mock_publish:
        await client.sleep(30)

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/sleep"
    assert json.loads(payload) == {"sleep": 30}


@pytest.mark.asyncio
async def test_update_settings():
    """update_settings() should publish to {prefix}/settings."""
    client = _make_client()
    settings = {"BRI": 200, "MATP": False}
    with _patch_mqtt() as mock_publish:
        await client.update_settings(settings)

    _hass, topic, payload = mock_publish.call_args[0]
    assert topic == f"{PREFIX}/settings"
    assert json.loads(payload) == settings
