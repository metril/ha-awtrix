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
    ICON_BATTERY_FULL,
    ICON_CALENDAR,
    ICON_CLOCK,
    ICON_HOURGLASS,
    ICON_HUMIDITY,
    ICON_TEXT,
    ICON_THERMOMETER,
    TIME_FORMATS,
    WEATHER_ICON_MAP,
    WEATHER_OVERLAY_MAP,
)

_LOGGER = logging.getLogger(__name__)

# Base properties applied to all app payloads
_BASE_PROPS = {
    "textCase": 2,   # preserve original case
    "pushIcon": 2,   # icon scrolls with text
    "lifetime": 0,   # don't auto-expire
}


class AwtrixAppManager:
    """Manages built-in app templates that push HA entity data to AWTRIX."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AwtrixClient,
        apps_config: dict,
        icon_client=None,
    ) -> None:
        self._hass = hass
        self._client = client
        self._apps_config = apps_config
        self._icon_client = icon_client or client
        self._unsub_listeners: list[Any] = []
        self._active_apps: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_start(self) -> None:
        """Push initial state and register listeners for all enabled apps."""
        # Collect and provision icons for enabled templates
        icon_str_ids: set[str] = set()
        for app_name, cfg in self._apps_config.items():
            if not cfg.get("enabled"):
                continue
            if app_name == "weather":
                icon_str_ids.update(WEATHER_ICON_MAP.values())
            elif app_name == "temperature":
                icon_str_ids.add(ICON_THERMOMETER)
            elif app_name == "humidity":
                icon_str_ids.add(ICON_HUMIDITY)
            elif app_name == "battery":
                icon_str_ids.add(ICON_BATTERY_FULL)
            elif app_name == "date":
                icon_str_ids.add(ICON_CALENDAR)
            elif app_name == "time":
                icon_str_ids.add(ICON_CLOCK)
            elif app_name == "countdown":
                icon_str_ids.add(ICON_HOURGLASS)
            elif app_name == "text":
                icon_str_ids.add(ICON_TEXT)

        if icon_str_ids:
            try:
                await self._icon_client.ensure_icons(sorted(int(i) for i in icon_str_ids))
            except Exception:
                _LOGGER.warning("Icon provisioning failed, continuing without icons")

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
            payload = {
                "text": text,
                "center": True,
                "noScroll": True,
                "textCase": 2,
                "lifetime": 0,
                "color": [255, 200, 50],
            }
            return self._apply_display_config(payload, cfg)
        if app_name == "time":
            fmt = cfg.get("format", next(iter(TIME_FORMATS)))
            text = dt_now().strftime(fmt)
            payload = {
                "text": text,
                "center": True,
                "noScroll": True,
                "textCase": 2,
                "lifetime": 0,
                "color": [255, 255, 255],
            }
            return self._apply_display_config(payload, cfg)
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
            text = f"H:{hi} L:{lo}"
        elif state is not None:
            temp = state.attributes.get("temperature", "")
            unit = state.attributes.get("temperature_unit", "°")
            text = f"{temp}{unit}"
        else:
            return

        payload = {
            "icon": icon,
            "text": text,
            "pushIcon": 0,
            "noScroll": True,
            "textCase": 2,
            "lifetime": 0,
        }
        payload = self._apply_display_config(payload, cfg)
        await self._send_app("weather_today", payload)

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
    # Display config helper
    # ------------------------------------------------------------------

    def _apply_display_config(self, payload: dict, cfg: dict) -> dict:
        """Apply user display preferences to payload."""
        color = cfg.get("text_color")
        if color:
            payload["color"] = color  # already [R, G, B] from config
        duration = cfg.get("display_duration", 0)
        if duration > 0:
            payload["duration"] = duration
        scroll_speed = cfg.get("scroll_speed", 100)
        if scroll_speed != 100:
            payload["scrollSpeed"] = scroll_speed
        return payload

    # ------------------------------------------------------------------
    # Weather payload builders
    # ------------------------------------------------------------------

    def _get_weather_icon(self, condition: str, cfg: dict) -> int:
        overrides = cfg.get("icon_overrides", {})
        icon = overrides.get(condition) or WEATHER_ICON_MAP.get(condition, 2283)
        return icon

    def _build_weather_current_payload(
        self, state, cfg: dict
    ) -> dict | None:
        """Build payload for the 'current' weather mode."""
        condition = state.state
        icon = self._get_weather_icon(condition, cfg)
        temp = state.attributes.get("temperature", "")
        unit = state.attributes.get("temperature_unit", "°")

        # Compact: just temp. Condition shown by icon.
        if cfg.get("show_condition_text", False):
            cond_text = condition.replace("-", " ").title()
            text = f"{temp}{unit} {cond_text}"
        else:
            text = f"{temp}{unit}"

        payload = {
            "icon": icon,
            "text": text,
            "pushIcon": 0,  # static icon for current weather
            "noScroll": not cfg.get("show_condition_text", False),
            "textCase": 2,
            "lifetime": 0,
        }

        # Weather overlay (rain/snow/storm effect)
        if cfg.get("weather_overlay", False):
            overlay = WEATHER_OVERLAY_MAP.get(condition)
            if overlay:
                payload["overlay"] = overlay

        # Temperature-based color: blue for cold, green for mild, red for hot
        if not cfg.get("text_color"):
            try:
                t = float(temp)
                if t < 32:  # freezing
                    payload["color"] = [0, 100, 255]
                elif t < 60:
                    payload["color"] = [0, 200, 255]
                elif t < 80:
                    payload["color"] = [0, 255, 100]
                else:
                    payload["color"] = [255, 80, 0]
            except (ValueError, TypeError):
                pass

        return self._apply_display_config(payload, cfg)

    def _build_weather_forecast_payload(
        self, cfg: dict, mode: str, forecasts: list[dict]
    ) -> dict | None:
        if not forecasts:
            return None

        if mode == "hourly":
            count = cfg.get("hourly_count", 4)
            parts: list[str] = []
            for fc in forecasts[:count]:
                dt_str = fc.get("datetime", "")
                try:
                    dt = datetime.fromisoformat(dt_str)
                    hour = dt.strftime("%-I%p")[:-1]  # e.g. "2P", "3P"
                except (ValueError, TypeError):
                    hour = dt_str[:5]
                temp = fc.get("temperature", "?")
                parts.append(f"{hour} {temp}\u00b0")
            payload = {
                "icon": ICON_CLOCK,
                "text": " ".join(parts),
                "textCase": 2,
                "pushIcon": 2,
                "lifetime": 0,
                "scrollSpeed": cfg.get("scroll_speed", 80),
            }
            return self._apply_display_config(payload, cfg)

        if mode == "daily":
            count = cfg.get("daily_count", 5)
            parts = []
            for fc in forecasts[:count]:
                dt_str = fc.get("datetime", "")
                try:
                    dt = datetime.fromisoformat(dt_str)
                    day = dt.strftime("%a")[:2]  # e.g. "Mo", "Tu"
                except (ValueError, TypeError):
                    day = dt_str[:2]
                hi = fc.get("temperature", "?")
                lo = fc.get("templow", "?")
                parts.append(f"{day} {hi}/{lo}")
            payload = {
                "icon": ICON_CALENDAR,
                "text": " ".join(parts),
                "textCase": 2,
                "pushIcon": 2,
                "lifetime": 0,
                "scrollSpeed": cfg.get("scroll_speed", 80),
            }
            return self._apply_display_config(payload, cfg)

        return None

    # ------------------------------------------------------------------
    # Simple template payload builders
    # ------------------------------------------------------------------

    def _build_temperature_payload(self, state, cfg: dict) -> dict | None:
        try:
            val = round(float(state.state), 1)
            text = f"{val}\u00b0"
        except (ValueError, TypeError):
            text = f"{state.state}\u00b0"

        payload = {
            "icon": ICON_THERMOMETER,
            "text": text,
            "pushIcon": 0,
            "noScroll": True,
            "textCase": 2,
            "lifetime": 0,
        }

        # Color based on temp value
        if not cfg.get("text_color"):
            try:
                t = float(state.state)
                if t < 0:
                    payload["color"] = [0, 100, 255]
                elif t < 15:
                    payload["color"] = [0, 200, 255]
                elif t < 25:
                    payload["color"] = [0, 255, 100]
                else:
                    payload["color"] = [255, 80, 0]
            except (ValueError, TypeError):
                pass

        return self._apply_display_config(payload, cfg)

    def _build_humidity_payload(self, state, cfg: dict) -> dict | None:
        text = f"{state.state}%"
        payload = {
            "icon": ICON_HUMIDITY,
            "text": text,
            "pushIcon": 0,
            "noScroll": True,
            "textCase": 2,
            "lifetime": 0,
            "color": [0, 150, 255],  # blue default for humidity
        }
        return self._apply_display_config(payload, cfg)

    def _build_battery_payload(self, state, cfg: dict) -> dict | None:
        try:
            pct = int(float(state.state))
        except (ValueError, TypeError):
            return None

        if pct > 50:
            bar_color = [0, 255, 0]
        elif pct >= 20:
            bar_color = [255, 255, 0]
        else:
            bar_color = [255, 0, 0]

        payload = {
            "icon": ICON_BATTERY_FULL,
            "text": f"{pct}%",
            "pushIcon": 0,
            "noScroll": True,
            "progress": pct,
            "progressC": bar_color,
            "progressBC": [50, 50, 50],
            "textCase": 2,
            "lifetime": 0,
        }
        return self._apply_display_config(payload, cfg)

    def _build_countdown_payload(self, state, cfg: dict) -> dict | None:
        payload = {
            "icon": ICON_HOURGLASS,
            "text": state.state,
            "textCase": 2,
            "pushIcon": 2,
            "lifetime": 0,
        }
        return self._apply_display_config(payload, cfg)

    def _build_text_payload(self, state, cfg: dict) -> dict | None:
        payload = {
            "icon": ICON_TEXT,
            "text": state.state,
            "textCase": 2,
            "pushIcon": 2,
            "lifetime": 0,
        }
        return self._apply_display_config(payload, cfg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send_app(self, app_name: str, payload: dict) -> None:
        try:
            await self._client.send_app(app_name, payload)
            self._active_apps.add(app_name)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to send app '%s' to device", app_name)
