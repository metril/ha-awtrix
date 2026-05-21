"""Tests for the AWTRIX app manager payload builders."""

from __future__ import annotations

import sys
import os

# Allow importing the custom component without Home Assistant installed.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from custom_components.awtrix.app_manager import AwtrixAppManager
from custom_components.awtrix.const import DATE_FORMATS


@pytest.fixture
def manager() -> AwtrixAppManager:
    """An app manager with mocked hass/client (payload builders need neither)."""
    return AwtrixAppManager(MagicMock(), MagicMock(), {})


def test_date_payload_scrolls_and_uses_default_format(manager: AwtrixAppManager) -> None:
    """Date must allow scrolling so long dates aren't clipped (regression: 05/20/2026 -> 05/20/20)."""
    fixed = datetime(2026, 5, 20)
    with patch(
        "custom_components.awtrix.app_manager.dt_now", return_value=fixed
    ):
        payload = manager._build_time_or_date_payload("date", {})

    # noScroll must be False so the firmware scrolls overflow instead of clipping it.
    assert payload["noScroll"] is False
    assert payload["center"] is True
    # Default format is the short 2-digit-year US date.
    assert payload["text"] == fixed.strftime("%m/%d/%y") == "05/20/26"


def test_date_payload_long_format_scrolls(manager: AwtrixAppManager) -> None:
    """A long, explicitly selected format still scrolls rather than clips."""
    fixed = datetime(2026, 5, 20)
    with patch(
        "custom_components.awtrix.app_manager.dt_now", return_value=fixed
    ):
        payload = manager._build_time_or_date_payload("date", {"format": "%Y-%m-%d"})

    assert payload["noScroll"] is False
    assert payload["text"] == "2026-05-20"


def test_time_payload_scrolls(manager: AwtrixAppManager) -> None:
    """Time payload must also allow scrolling (e.g. %H:%M:%S would otherwise clip)."""
    fixed = datetime(2026, 5, 20, 14, 30, 45)
    with patch(
        "custom_components.awtrix.app_manager.dt_now", return_value=fixed
    ):
        payload = manager._build_time_or_date_payload("time", {})

    assert payload["noScroll"] is False
    assert payload["center"] is True


def test_default_date_format_is_short_two_digit_year() -> None:
    """Lock in the new default to prevent the clipping default from returning."""
    assert next(iter(DATE_FORMATS)) == "%m/%d/%y"
