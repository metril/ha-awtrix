"""Tests for presence filtering, MQTT uid normalisation, and auth failure handling."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.awtrix.__init__ import presence_to_matp
from custom_components.awtrix.client import AwtrixApiError, AwtrixConnectionError
from custom_components.awtrix.config_flow import normalize_device_uid
from custom_components.awtrix.coordinator import AwtrixCoordinator


@pytest.mark.parametrize(
    ("state", "expected"),
    [("on", True), ("off", False), ("unavailable", None), ("unknown", None)],
)
def test_presence_filter(state, expected):
    assert presence_to_matp(SimpleNamespace(state=state)) is expected


def test_presence_none_state():
    assert presence_to_matp(None) is None


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        ({"ids": ["awtrix_abc123"]}, "awtrix_abc123"),
        ({"ids": "awtrix_abc123"}, "awtrix_abc123"),
        ({"identifiers": ["awtrix_abc123", "x"]}, "awtrix_abc123"),
        ({}, ""),
    ],
)
def test_unique_id_normalised(info, expected):
    assert normalize_device_uid(info) == expected


def _coordinator(client, connection_type="http"):
    entry = SimpleNamespace(title="t")
    return AwtrixCoordinator(MagicMock(), entry, client, connection_type=connection_type)


def test_401_raises_auth_failed():
    client = MagicMock()
    client.get_stats = AsyncMock(
        side_effect=AwtrixApiError("AWTRIX API returned status 401 for GET http://x", 401)
    )
    client.get_settings = AsyncMock(return_value={})
    with pytest.raises(ConfigEntryAuthFailed):
        asyncio.run(_coordinator(client)._async_update_data())


def test_other_errors_are_update_failed():
    client = MagicMock()
    client.get_stats = AsyncMock(side_effect=AwtrixConnectionError("down"))
    client.get_settings = AsyncMock(return_value={})
    with pytest.raises(UpdateFailed):
        asyncio.run(_coordinator(client)._async_update_data())


def test_mqtt_stale_marks_offline(monkeypatch):
    coord = _coordinator(MagicMock(), "mqtt")
    coord.async_update_listeners = MagicMock()
    assert coord.device_online
    coord._last_stats_time -= 1000
    coord._check_mqtt_stale()
    assert not coord.device_online
    coord.async_update_listeners.assert_called_once()
