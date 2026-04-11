"""AWTRIX App Manager — pushes HA entity data to built-in app templates."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util.dt import now as dt_now

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .client import AwtrixClient
from .const import (
    DATE_FORMATS,
    ICON_BATTERY,
    ICON_CALENDAR,
    ICON_CLOCK,
    ICON_HOURGLASS,
    ICON_HUMIDITY,
    ICON_TEXT,
    ICON_THERMOMETER,
    TIME_FORMATS,
    WEATHER_ICON_MAP,
)

_LOGGER = logging.getLogger(__name__)


class AwtrixAppManager:
    """Manages built-in app templates that push HA entity data to AWTRIX."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AwtrixClient,
        apps_config: dict,
    ) -> None:
        self._hass = hass
        self._client = client
        self._apps_config = apps_config
        self._unsub_listeners: list[Any] = []
        self._active_apps: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_start(self) -> None:
        """Push initial state and register listeners for all enabled apps."""
        for app_name, cfg in self._apps_config.items():
            if not cfg.get("enabled"):
                continue
            try:
                await self._setup_app(app_name, cfg)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Error setting up app template '%s'", app_name)

    async def async_stop(self) -> None:
        """Unsubscribe all listeners and remove active apps from the device."""
        for unsub in self._unsub_listeners:
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
        self._unsub_listeners.clear()

        for app_name in list(self._active_apps):
            try:
                await self._client.remove_app(app_name)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to remove app '%s' on stop", app_name)
        self._active_apps.clear()

    # ------------------------------------------------------------------
    # App setup dispatch
    # ------------------------------------------------------------------

    async def _setup_app(self, app_name: str, cfg: dict) -> None:
        """Set up a single app template."""
        if app_name == "weather":
            await self._setup_weather(cfg)
        elif app_name == "temperature":
            await self._setup_entity_app(app_name, cfg, self._build_temperature_payload)
        elif app_name == "humidity":
            await self._setup_entity_app(app_name, cfg, self._build_humidity_payload)
        elif app_name == "battery":
            await self._setup_entity_app(app_name, cfg, self._build_battery_payload)
        elif app_name == "date":
            await self._setup_time_app(app_name, cfg, timedelta(seconds=60))
        elif app_name == "time":
            await self._setup_time_app(app_name, cfg, timedelta(seconds=30))
        elif app_name == "countdown":
            await self._setup_entity_app(app_name, cfg, self._build_countdown_payload)
        elif app_name == "text":
            await self._setup_entity_app(app_name, cfg, self._build_text_payload)

    # ------------------------------------------------------------------
    # Generic entity-backed setup
    # ------------------------------------------------------------------

    async def _setup_entity_app(self, app_name: str, cfg: dict, builder) -> None:
        """Push initial payload and subscribe to state changes for an entity app."""
        entity_id = cfg.get("entity_id")
        if not entity_id:
            return

        # Push initial state
        state = self._hass.states.get(entity_id)
        if state is not None:
            payload = builder(state, cfg)
            if payload:
                await self._send_app(app_name, payload)

        # Subscribe to future changes
        @callback
        def _on_state_change(event):
            new_state = event.data.get("new_state")
            if new_state is None:
                return
            p = builder(new_state, cfg)
            if p:
                self._hass.async_create_task(self._send_app(app_name, p))

        unsub = async_track_state_change_event(self._hass, entity_id, _on_state_change)
        self._unsub_listeners.append(unsub)

    # ------------------------------------------------------------------
    # Time/date apps (periodic)
    # ------------------------------------------------------------------

    async def _setup_time_app(
        self, app_name: str, cfg: dict, interval: timedelta
    ) -> None:
        """Push initial time/date and set up periodic refresh."""
        payload = self._build_time_or_date_payload(app_name, cfg)
        if payload:
            await self._send_app(app_name, payload)

        @callback
        def _tick(_now):
            p = self._build_time_or_date_payload(app_name, cfg)
            if p:
                self._hass.async_create_task(self._send_app(app_name, p))

        unsub = async_track_time_interval(self._hass, _tick, interval)
        self._unsub_listeners.append(unsub)

    def _build_time_or_date_payload(self, app_name: str, cfg: dict) -> dict | None:
        if app_name == "date":
            fmt = cfg.get("format", next(iter(DATE_FORMATS)))
            text = dt_now().strftime(fmt)
            return {"icon": ICON_CALENDAR, "text": text}
        if app_name == "time":
            fmt = cfg.get("format", next(iter(TIME_FORMATS)))
            text = dt_now().strftime(fmt)
            return {"icon": ICON_CLOCK, "text": text}
        return None

    # ------------------------------------------------------------------
    # Weather setup (multi-mode, multi-app)
    # ------------------------------------------------------------------

    async def _setup_weather(self, cfg: dict) -> None:
        """Set up one or more weather sub-apps based on selected modes."""
        entity_id = cfg.get("entity_id")
        if not entity_id:
            return

        modes = cfg.get("modes", ["current"])

        # Push initial state for all modes
        await self._push_weather_modes(entity_id, cfg, modes)

        # Subscribe to state changes for current/today modes
        entity_modes = [m for m in modes if m in ("current", "today")]
        if entity_modes:
            @callback
            def _on_weather_change(event):
                new_state = event.data.get("new_state")
                if new_state is None:
                    return
                for mode in entity_modes:
                    if mode == "current":
                        p = self._build_weather_current_payload(new_state, cfg)
                        if p:
                            self._hass.async_create_task(
                                self._send_app("weather_current", p)
                            )
                    elif mode == "today":
                        self._hass.async_create_task(
                            self._push_weather_today(entity_id, cfg, new_state)
                        )

            unsub = async_track_state_change_event(
                self._hass, entity_id, _on_weather_change
            )
            self._unsub_listeners.append(unsub)

        # Periodic refresh for forecast modes
        forecast_modes = [m for m in modes if m in ("hourly", "daily")]
        if forecast_modes:
            @callback
            def _refresh_forecasts(_now):
                self._hass.async_create_task(
                    self._push_weather_forecast_modes(entity_id, cfg, forecast_modes)
                )

            unsub = async_track_time_interval(
                self._hass, _refresh_forecasts, timedelta(minutes=30)
            )
            self._unsub_listeners.append(unsub)

    async def _push_weather_modes(
        self, entity_id: str, cfg: dict, modes: list[str]
    ) -> None:
        state = self._hass.states.get(entity_id)

        for mode in modes:
            if mode == "current":
                if state is not None:
                    p = self._build_weather_current_payload(state, cfg)
                    if p:
                        await self._send_app(f"weather_{mode}", p)
            elif mode == "today":
                await self._push_weather_today(entity_id, cfg, state)
            elif mode in ("hourly", "daily"):
                await self._push_weather_forecast_mode(entity_id, cfg, mode)

    async def _push_weather_forecast_modes(
        self, entity_id: str, cfg: dict, modes: list[str]
    ) -> None:
        for mode in modes:
            await self._push_weather_forecast_mode(entity_id, cfg, mode)

    async def _push_weather_today(
        self, entity_id: str, cfg: dict, state
    ) -> None:
        """Fetch today's daily forecast and push the weather_today app."""
        try:
            result = await self._hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": "daily"},
                blocking=True,
                return_response=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to fetch daily forecast for %s (today mode)", entity_id)
            result = None

        forecasts: list[dict] = []
        if result and isinstance(result, dict):
            forecasts = result.get(entity_id, {}).get("forecast", [])

        condition = state.state if state is not None else "unknown"
        icon = self._get_weather_icon(condition, cfg)

        if forecasts:
            today = forecasts[0]
            hi = today.get("temperature", "?")
            lo = today.get("templow", "?")
            unit = (state.attributes.get("temperature_unit", "°") if state is not None else "°")
            detail = today.get("condition", condition).replace("-", " ").title()
            text = f"\u2191{hi}{unit} \u2193{lo}{unit} {detail}"
        elif state is not None:
            temp = state.attributes.get("temperature", "")
            unit = state.attributes.get("temperature_unit", "°")
            text = f"{temp}{unit} {condition.replace('-', ' ').title()}"
        else:
            return

        p = {"icon": icon, "text": text}
        await self._send_app("weather_today", p)

    async def _push_weather_forecast_mode(
        self, entity_id: str, cfg: dict, mode: str
    ) -> None:
        forecast_type = "hourly" if mode == "hourly" else "daily"
        try:
            result = await self._hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": forecast_type},
                blocking=True,
                return_response=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Failed to fetch %s forecast for %s", forecast_type, entity_id
            )
            return

        forecasts: list[dict] = []
        if result and isinstance(result, dict):
            forecasts = result.get(entity_id, {}).get("forecast", [])

        p = self._build_weather_forecast_payload(cfg, mode, forecasts)
        if p:
            await self._send_app(f"weather_{mode}", p)

    # ------------------------------------------------------------------
    # Weather payload builders
    # ------------------------------------------------------------------

    def _get_weather_icon(self, condition: str, cfg: dict) -> str:
        overrides = cfg.get("icon_overrides", {})
        icon = overrides.get(condition) or WEATHER_ICON_MAP.get(condition, "2283")
        return icon

    def _build_weather_current_payload(
        self, state, cfg: dict
    ) -> dict | None:
        """Build payload for the 'current' weather mode."""
        condition = state.state
        icon = self._get_weather_icon(condition, cfg)
        temp = state.attributes.get("temperature", "")
        unit = state.attributes.get("temperature_unit", "°")
        text = f"{temp}{unit} {condition.replace('-', ' ').title()}"
        return {"icon": icon, "text": text}

    def _build_weather_forecast_payload(
        self, cfg: dict, mode: str, forecasts: list[dict]
    ) -> dict | None:
        if not forecasts:
            return None

        if mode == "hourly":
            count = cfg.get("hourly_count", 4)
            parts: list[str] = []
            for fc in forecasts[:count]:
                # datetime string e.g. "2026-04-10T14:00:00"
                dt_str = fc.get("datetime", "")
                try:
                    dt = datetime.fromisoformat(dt_str)
                    label = dt.strftime("%-I%p").replace("AM", "AM").replace("PM", "PM")
                except (ValueError, TypeError):
                    label = dt_str[:5]
                temp = fc.get("temperature", "?")
                parts.append(f"{label} {temp}\u00b0")
            return {"icon": ICON_CLOCK, "text": "  ".join(parts), "scrollSpeed": 50}

        if mode == "daily":
            count = cfg.get("daily_count", 5)
            parts = []
            for fc in forecasts[:count]:
                dt_str = fc.get("datetime", "")
                try:
                    dt = datetime.fromisoformat(dt_str)
                    day = dt.strftime("%a")
                except (ValueError, TypeError):
                    day = dt_str[:3]
                hi = fc.get("temperature", "?")
                lo = fc.get("templow", "?")
                parts.append(f"{day} \u2191{hi}\u00b0 \u2193{lo}\u00b0")
            return {"icon": ICON_CALENDAR, "text": "  ".join(parts), "scrollSpeed": 50}

        return None

    # ------------------------------------------------------------------
    # Simple template payload builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_temperature_payload(state, _cfg: dict) -> dict | None:
        value = state.state
        unit = state.attributes.get("unit_of_measurement", "°")
        return {"icon": ICON_THERMOMETER, "text": f"{value}{unit}"}

    @staticmethod
    def _build_humidity_payload(state, _cfg: dict) -> dict | None:
        value = state.state
        unit = state.attributes.get("unit_of_measurement", "%")
        return {"icon": ICON_HUMIDITY, "text": f"{value}{unit}"}

    @staticmethod
    def _build_battery_payload(state, _cfg: dict) -> dict | None:
        try:
            pct = float(state.state)
        except (ValueError, TypeError):
            return None
        if pct > 50:
            color = [0, 255, 0]
        elif pct >= 20:
            color = [255, 255, 0]
        else:
            color = [255, 0, 0]
        return {"icon": ICON_BATTERY, "text": f"{int(pct)}%", "color": color}

    @staticmethod
    def _build_countdown_payload(state, _cfg: dict) -> dict | None:
        return {"icon": ICON_HOURGLASS, "text": state.state}

    @staticmethod
    def _build_text_payload(state, _cfg: dict) -> dict | None:
        return {"icon": ICON_TEXT, "text": state.state}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send_app(self, app_name: str, payload: dict) -> None:
        try:
            await self._client.send_app(app_name, payload)
            self._active_apps.add(app_name)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to send app '%s' to device", app_name)
