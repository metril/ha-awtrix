"""Tests for the reauth flow."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.awtrix import config_flow
from custom_components.awtrix.client import AwtrixApiError, AwtrixConnectionError
from custom_components.awtrix.config_flow import AwtrixConfigFlow


def _flow(data):
    entry = SimpleNamespace(data=data)
    flow = AwtrixConfigFlow()
    flow.hass = MagicMock()
    flow._get_reauth_entry = lambda: entry
    flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})
    flow.async_show_form = MagicMock(side_effect=lambda **kw: {"type": "form", **kw})
    return flow, entry


def _run(flow, get_stats, user_input):
    client = MagicMock()
    client.get_stats = get_stats
    with patch.object(config_flow, "AwtrixHttpClient", return_value=client):
        return asyncio.run(flow.async_step_reauth_confirm(user_input))


def test_reauth_success_updates_and_aborts():
    flow, entry = _flow({"host": "1.2.3.4", "port": 80})
    res = _run(flow, AsyncMock(return_value=MagicMock()), {"username": "u", "password": "p"})
    assert res == {"type": "abort"}
    flow.async_update_reload_and_abort.assert_called_once()
    assert flow.async_update_reload_and_abort.call_args.args[0] is entry
    assert flow.async_update_reload_and_abort.call_args.kwargs["data"] == {
        "host": "1.2.3.4",
        "port": 80,
        "username": "u",
        "password": "p",
    }


def test_reauth_blank_clears_credentials():
    flow, _ = _flow({"host": "1.2.3.4", "username": "old", "password": "old"})
    _run(flow, AsyncMock(return_value=MagicMock()), {"username": "", "password": ""})
    assert flow.async_update_reload_and_abort.call_args.kwargs["data"] == {"host": "1.2.3.4"}


def test_reauth_401_shows_invalid_auth():
    flow, _ = _flow({"host": "1.2.3.4"})
    err = AwtrixApiError("401", 401)
    res = _run(flow, AsyncMock(side_effect=err), {"username": "u", "password": "bad"})
    assert res["errors"] == {"base": "invalid_auth"}
    flow.async_update_reload_and_abort.assert_not_called()


def test_reauth_connection_error_shows_cannot_connect():
    flow, _ = _flow({"host": "1.2.3.4"})
    res = _run(flow, AsyncMock(side_effect=AwtrixConnectionError("x")), {"username": "u", "password": "p"})
    assert res["errors"] == {"base": "cannot_connect"}


def test_reauth_mqtt_without_host_saves_unvalidated():
    flow, _ = _flow({"mqtt_prefix": "awtrix"})
    res = asyncio.run(flow.async_step_reauth_confirm({"username": "u", "password": "p"}))
    assert res == {"type": "abort"}
