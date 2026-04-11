"""Tests for the AWTRIX HTTP client."""

from __future__ import annotations

import sys
import os

# Allow importing the custom component without Home Assistant installed.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from custom_components.awtrix.client import (
    AwtrixHttpClient,
    AwtrixConnectionError,
    AwtrixApiError,
)
from custom_components.awtrix.models import AwtrixStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(status: int = 200, json_data=None, raw_bytes: bytes = b""):
    """Return a mock aiohttp.ClientSession and the underlying mock response.

    The session.request() is set up as an async context manager so that
    ``async with session.request(...) as resp:`` works correctly.
    """
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_data)
    mock_response.read = AsyncMock(return_value=raw_bytes)

    # Set Content-Type so _request knows which branch to take.
    headers = {"Content-Type": "application/json"} if json_data is not None else {}
    mock_response.headers = headers

    # Build the async context manager returned by session.request(...)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_response)
    cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.request = MagicMock(return_value=cm)
    return session, mock_response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_stats():
    """get_stats() should parse the response into AwtrixStats and call /api/stats."""
    stats_payload = {
        "uid": "AABB",
        "bat": 85,
        "bat_raw": 700,
        "lux": 300,
        "ldr_raw": 512,
        "ram": 140000,
        "bri": 120,
        "temp": 22.5,
        "hum": 45.0,
        "uptime": 3600,
        "wifi_signal": -55,
        "version": "0.98",
        "ip_address": "192.168.1.50",
        "currentApp": "clock",
    }
    session, _ = _make_session(json_data=stats_payload)
    client = AwtrixHttpClient(session, "192.168.1.50")

    result = await client.get_stats()

    assert isinstance(result, AwtrixStats)
    assert result.uid == "AABB"
    assert result.battery == 85
    assert result.temperature == 22.5
    assert result.firmware == "0.98"
    assert result.current_app == "clock"

    # Verify the correct URL was requested
    call_args = session.request.call_args
    assert call_args[0][0] == "GET"
    assert call_args[0][1] == "http://192.168.1.50:80/api/stats"


@pytest.mark.asyncio
async def test_get_stats_connection_error():
    """A ClientConnectorError should be re-raised as AwtrixConnectionError."""
    session = MagicMock()
    session.request = MagicMock(
        side_effect=aiohttp.ClientConnectorError(
            connection_key=MagicMock(), os_error=OSError("refused")
        )
    )
    client = AwtrixHttpClient(session, "192.168.1.50")

    with pytest.raises(AwtrixConnectionError):
        await client.get_stats()


@pytest.mark.asyncio
async def test_set_power():
    """set_power() should POST to /api/power with {power: <bool>}."""
    session, _ = _make_session()
    client = AwtrixHttpClient(session, "192.168.1.50")

    await client.set_power(True)

    call_args = session.request.call_args
    assert call_args[0][0] == "POST"
    assert call_args[0][1] == "http://192.168.1.50:80/api/power"
    assert call_args[1]["json"] == {"power": True}


@pytest.mark.asyncio
async def test_send_notification():
    """send_notification() should POST to /api/notify with the payload."""
    payload = {"text": "Hello!", "color": "#FF0000"}
    session, _ = _make_session()
    client = AwtrixHttpClient(session, "192.168.1.50")

    await client.send_notification(payload)

    call_args = session.request.call_args
    assert call_args[0][0] == "POST"
    assert call_args[0][1] == "http://192.168.1.50:80/api/notify"
    assert call_args[1]["json"] == payload


@pytest.mark.asyncio
async def test_send_app():
    """send_app() should POST to /api/custom with query param name=weather."""
    payload = {"text": "Sunny", "icon": "2283"}
    session, _ = _make_session()
    client = AwtrixHttpClient(session, "192.168.1.50")

    await client.send_app("weather", payload)

    call_args = session.request.call_args
    assert call_args[0][0] == "POST"
    assert call_args[0][1] == "http://192.168.1.50:80/api/custom"
    assert call_args[1]["params"] == {"name": "weather"}
    assert call_args[1]["json"] == payload


@pytest.mark.asyncio
async def test_remove_app():
    """remove_app() should POST an empty dict payload."""
    session, _ = _make_session()
    client = AwtrixHttpClient(session, "192.168.1.50")

    await client.remove_app("weather")

    call_args = session.request.call_args
    assert call_args[0][0] == "POST"
    assert call_args[0][1] == "http://192.168.1.50:80/api/custom"
    assert call_args[1]["params"] == {"name": "weather"}
    assert call_args[1]["json"] == {}


@pytest.mark.asyncio
async def test_set_indicator():
    """set_indicator() should POST /api/indicator<n> with the colour."""
    session, _ = _make_session()
    client = AwtrixHttpClient(session, "192.168.1.50")

    await client.set_indicator(1, [255, 0, 0])

    call_args = session.request.call_args
    assert call_args[0][0] == "POST"
    assert call_args[0][1] == "http://192.168.1.50:80/api/indicator1"
    assert call_args[1]["json"] == {"color": [255, 0, 0]}


@pytest.mark.asyncio
async def test_set_indicator_off():
    """set_indicator() with None should POST an empty dict to clear the indicator."""
    session, _ = _make_session()
    client = AwtrixHttpClient(session, "192.168.1.50")

    await client.set_indicator(2, None)

    call_args = session.request.call_args
    assert call_args[0][1] == "http://192.168.1.50:80/api/indicator2"
    assert call_args[1]["json"] == {}


@pytest.mark.asyncio
async def test_api_error_on_non_200():
    """A non-200 response should raise AwtrixApiError."""
    session, _ = _make_session(status=500)
    client = AwtrixHttpClient(session, "192.168.1.50")

    with pytest.raises(AwtrixApiError):
        await client.get_stats()
