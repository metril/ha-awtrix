"""AWTRIX client abstraction layer."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import aiohttp

from .models import AwtrixStats

_LOGGER = logging.getLogger(__name__)


class AwtrixConnectionError(Exception):
    """Raised when a connection to the AWTRIX device cannot be established."""


class AwtrixApiError(Exception):
    """Raised when the AWTRIX API returns a non-200 response."""


class AwtrixClient(ABC):
    """Abstract base class for AWTRIX clients."""

    @abstractmethod
    async def get_stats(self) -> AwtrixStats:
        """Return device statistics."""

    @abstractmethod
    async def get_settings(self) -> dict:
        """Return current device settings."""

    @abstractmethod
    async def get_effects(self) -> list[str]:
        """Return list of available effects."""

    @abstractmethod
    async def get_transitions(self) -> list[str]:
        """Return list of available transition effects."""

    @abstractmethod
    async def set_power(self, on: bool) -> None:
        """Turn the display on or off."""

    @abstractmethod
    async def send_app(self, name: str, payload: dict) -> None:
        """Push a custom app to the device."""

    @abstractmethod
    async def remove_app(self, name: str) -> None:
        """Remove a custom app from the device (sends empty payload)."""

    @abstractmethod
    async def send_notification(self, payload: dict) -> None:
        """Send a notification to the device."""

    @abstractmethod
    async def dismiss_notification(self) -> None:
        """Dismiss the currently displayed notification."""

    @abstractmethod
    async def set_indicator(self, index: int, color: list[int] | None) -> None:
        """Set or clear an indicator LED."""

    @abstractmethod
    async def set_moodlight(self, payload: dict | None) -> None:
        """Set mood light configuration. None disables moodlight."""

    @abstractmethod
    async def play_sound(self, sound: str) -> None:
        """Play a sound by name."""

    @abstractmethod
    async def play_rtttl(self, melody: str) -> None:
        """Play a melody in RTTTL format."""

    @abstractmethod
    async def next_app(self) -> None:
        """Switch to the next app."""

    @abstractmethod
    async def previous_app(self) -> None:
        """Switch to the previous app."""

    @abstractmethod
    async def switch_app(self, name: str) -> None:
        """Switch to a specific app by name."""

    @abstractmethod
    async def update_settings(self, settings: dict) -> None:
        """Update device settings."""

    @abstractmethod
    async def sleep(self, seconds: int) -> None:
        """Put the device to sleep for the given number of seconds."""

    @abstractmethod
    async def reboot(self) -> None:
        """Reboot the device."""

    @abstractmethod
    async def get_screen(self) -> bytes:
        """Return a screenshot of the current display."""

    @abstractmethod
    async def ensure_icons(self, icon_ids: list[int]) -> None:
        """Ensure icons are available on the device."""


class _AwtrixResponse:
    """Lightweight container for a consumed aiohttp response."""

    __slots__ = ("status", "_json_data", "_raw_bytes", "_method", "_url")

    def __init__(
        self,
        status: int,
        json_data,
        raw_bytes: bytes,
        method: str,
        url: str,
    ) -> None:
        self.status = status
        self._json_data = json_data
        self._raw_bytes = raw_bytes
        self._method = method
        self._url = url

    async def json(self):
        return self._json_data

    async def read(self) -> bytes:
        return self._raw_bytes


class AwtrixHttpClient(AwtrixClient):
    """HTTP implementation of the AWTRIX client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int = 80,
        timeout: int = 10,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialise the HTTP client."""
        self._session = session
        self._host = host
        self._port = port
        self._base_url = f"http://{host}:{port}/api"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        if username and password:
            self._auth: aiohttp.BasicAuth | None = aiohttp.BasicAuth(username, password)
        else:
            self._auth = None

    async def _request(self, method: str, path: str, **kwargs) -> _AwtrixResponse:
        """Perform an HTTP request and fully consume the response body.

        Raises:
            AwtrixConnectionError: if the device cannot be reached.
            AwtrixApiError: if the response status is not 200.
        """
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method, url, timeout=self._timeout, auth=self._auth, **kwargs
            ) as response:
                status = response.status
                if status != 200:
                    raise AwtrixApiError(
                        f"AWTRIX API returned status {status} for {method} {url}"
                    )
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    json_data = await response.json()
                    raw_bytes = b""
                else:
                    raw_bytes = await response.read()
                    json_data = None
                return _AwtrixResponse(status, json_data, raw_bytes, method, url)
        except AwtrixApiError:
            raise
        except aiohttp.ClientConnectorError as err:
            raise AwtrixConnectionError(
                f"Cannot connect to AWTRIX device at {url}"
            ) from err

    async def get_stats(self) -> AwtrixStats:
        """Return device statistics from /api/stats."""
        response = await self._request("GET", "/stats")
        data = await response.json()
        return AwtrixStats.from_dict(data)

    async def get_settings(self) -> dict:
        """Return current settings from /api/settings."""
        response = await self._request("GET", "/settings")
        return await response.json()

    async def get_effects(self) -> list[str]:
        """Return available effects from /api/effects."""
        response = await self._request("GET", "/effects")
        return await response.json()

    async def get_transitions(self) -> list[str]:
        """Return available transitions from /api/transitions."""
        response = await self._request("GET", "/transitions")
        return await response.json()

    async def set_power(self, on: bool) -> None:
        """POST /api/power with {power: <bool>}."""
        await self._request("POST", "/power", json={"power": on})

    async def send_app(self, name: str, payload: dict) -> None:
        """POST /api/custom?name=<name> with the app payload."""
        await self._request("POST", "/custom", params={"name": name}, json=payload)

    async def remove_app(self, name: str) -> None:
        """POST /api/custom?name=<name> with an empty payload to remove the app."""
        await self._request("POST", "/custom", params={"name": name}, json={})

    async def send_notification(self, payload: dict) -> None:
        """POST /api/notify with the notification payload."""
        await self._request("POST", "/notify", json=payload)

    async def dismiss_notification(self) -> None:
        """POST /api/notify/dismiss."""
        await self._request("POST", "/notify/dismiss")

    async def set_indicator(self, index: int, color: list[int] | None) -> None:
        """POST /api/indicator<index> with color or empty payload to clear."""
        payload = {"color": color} if color is not None else {}
        await self._request("POST", f"/indicator{index}", json=payload)

    async def set_moodlight(self, payload: dict | None) -> None:
        """POST /api/moodlight. None payload disables moodlight."""
        if payload is None:
            await self._request("POST", "/moodlight")
        else:
            await self._request("POST", "/moodlight", json=payload)

    async def play_sound(self, sound: str) -> None:
        """POST /api/sound with {sound: <name>}."""
        await self._request("POST", "/sound", json={"sound": sound})

    async def play_rtttl(self, melody: str) -> None:
        """POST /api/rtttl with the raw melody string."""
        await self._request("POST", "/rtttl", data=melody)

    async def next_app(self) -> None:
        """POST /api/nextapp."""
        await self._request("POST", "/nextapp")

    async def previous_app(self) -> None:
        """POST /api/previousapp."""
        await self._request("POST", "/previousapp")

    async def switch_app(self, name: str) -> None:
        """POST /api/switch with {name: <name>}."""
        await self._request("POST", "/switch", json={"name": name})

    async def update_settings(self, settings: dict) -> None:
        """POST /api/settings with the settings payload."""
        await self._request("POST", "/settings", json=settings)

    async def sleep(self, seconds: int) -> None:
        """POST /api/sleep with {sleep: <seconds>}."""
        await self._request("POST", "/sleep", json={"sleep": seconds})

    async def reboot(self) -> None:
        """POST /api/reboot."""
        await self._request("POST", "/reboot")

    async def get_screen(self) -> bytes:
        """GET /api/screen and return raw bytes."""
        response = await self._request("GET", "/screen")
        return await response.read()

    async def ensure_icons(self, icon_ids: list[int]) -> None:
        for icon_id in icon_ids:
            try:
                await self._ensure_single_icon(icon_id)
            except Exception:
                _LOGGER.warning("Failed to provision icon %s", icon_id, exc_info=True)

    async def _ensure_single_icon(self, icon_id: int) -> None:
        base = f"http://{self._host}:{self._port}"
        _LOGGER.info("Icon %s: checking existence on %s", icon_id, base)

        # Check if already exists via /list endpoint
        try:
            async with self._session.get(
                f"{base}/list?dir=/ICONS", timeout=self._timeout, auth=self._auth
            ) as resp:
                if resp.status == 200:
                    # AWTRIX returns text/json instead of application/json
                    files = await resp.json(content_type=None)
                    existing = {f.get("name", "") for f in files}
                    if f"{icon_id}.gif" in existing or f"{icon_id}.jpg" in existing:
                        _LOGGER.info("Icon %s: already on device, skipping", icon_id)
                        return
                    _LOGGER.info("Icon %s: not found in %d files on device", icon_id, len(files))
                else:
                    _LOGGER.info("Icon %s: /list returned HTTP %s", icon_id, resp.status)
        except Exception as err:
            _LOGGER.info("Icon %s: /list check failed: %s", icon_id, err)

        # Download from LaMetric
        from .const import LAMETRIC_ICON_URL
        dl_url = f"{LAMETRIC_ICON_URL}/{icon_id}"
        _LOGGER.info("Icon %s: downloading from %s", icon_id, dl_url)
        dl_timeout = aiohttp.ClientTimeout(total=15)
        async with self._session.get(dl_url, timeout=dl_timeout) as resp:
            if resp.status != 200:
                _LOGGER.warning("Icon %s: LaMetric download failed HTTP %s", icon_id, resp.status)
                return
            content_type = resp.content_type or ""
            icon_bytes = await resp.read()
            _LOGGER.info("Icon %s: downloaded %d bytes (%s)", icon_id, len(icon_bytes), content_type)

        ext = "gif" if "gif" in content_type else "jpg"
        filename = f"/ICONS/{icon_id}.{ext}"

        # Upload to device (field name must be "data", not "file")
        _LOGGER.info("Icon %s: uploading as %s to %s/edit", icon_id, filename, base)
        form = aiohttp.FormData(quote_fields=False)
        form.add_field("data", icon_bytes, filename=filename, content_type=content_type)
        async with self._session.post(f"{base}/edit", data=form, timeout=self._timeout, auth=self._auth) as resp:
            if resp.status == 200:
                _LOGGER.info("Icon %s: uploaded successfully", icon_id)
            else:
                body = await resp.text()
                _LOGGER.warning("Icon %s: upload failed HTTP %s: %s", icon_id, resp.status, body[:200])


class AwtrixMqttClient(AwtrixClient):
    """AWTRIX3 client using MQTT."""

    def __init__(self, hass: Any, prefix: str) -> None:
        self._hass = hass
        self._prefix = prefix
        self.last_stats: AwtrixStats | None = None
        self._last_settings: dict | None = None
        _LOGGER.info("AWTRIX MQTT client initialized with prefix: %r", prefix)

    async def _publish(self, topic: str, payload: str | None = None) -> None:
        """Publish a message to the given MQTT topic."""
        full_topic = f"{self._prefix}/{topic}"
        _LOGGER.debug(
            "AWTRIX MQTT publish: topic=%s payload=%s",
            full_topic,
            repr(payload[:200]) if payload else "(none)",
        )
        from homeassistant.components.mqtt import async_publish
        await async_publish(self._hass, full_topic, payload)

    def process_stats_message(self, payload: str) -> None:
        """Parse a stats MQTT message and store the result."""
        data = json.loads(payload)
        self.last_stats = AwtrixStats.from_dict(data)

    def process_settings_message(self, payload: str) -> None:
        """Parse a settings MQTT message and store the result."""
        self._last_settings = json.loads(payload)

    async def get_stats(self) -> AwtrixStats:
        """Return the last received stats, or an empty AwtrixStats."""
        return self.last_stats if self.last_stats is not None else AwtrixStats()

    async def get_settings(self) -> dict:
        """Return the last received settings, or an empty dict."""
        return self._last_settings if self._last_settings is not None else {}

    async def get_effects(self) -> list[str]:
        """Not available via MQTT; returns empty list."""
        return []

    async def get_transitions(self) -> list[str]:
        """Not available via MQTT; returns empty list."""
        return []

    async def set_power(self, on: bool) -> None:
        """Publish power command."""
        await self._publish("power", json.dumps({"power": on}))

    async def send_app(self, name: str, payload: dict) -> None:
        """Publish custom app payload."""
        await self._publish(f"custom/{name}", json.dumps(payload))

    async def remove_app(self, name: str) -> None:
        """Remove a custom app by sending an empty payload."""
        await self._publish(f"custom/{name}")

    async def send_notification(self, payload: dict) -> None:
        """Publish a notification."""
        await self._publish("notify", json.dumps(payload))

    async def dismiss_notification(self) -> None:
        """Dismiss the current notification."""
        await self._publish("notify/dismiss")

    async def set_indicator(self, index: int, color: list[int] | None) -> None:
        """Set or clear an indicator LED."""
        payload = {"color": color} if color is not None else {}
        await self._publish(f"indicator{index}", json.dumps(payload))

    async def set_moodlight(self, payload: dict | None) -> None:
        """Set mood light configuration. None disables moodlight."""
        if payload is None:
            await self._publish("moodlight")
        else:
            await self._publish("moodlight", json.dumps(payload))

    async def play_sound(self, sound: str) -> None:
        """Play a sound by name."""
        await self._publish("sound", json.dumps({"sound": sound}))

    async def play_rtttl(self, melody: str) -> None:
        """Play a melody in RTTTL format."""
        await self._publish("rtttl", melody)

    async def next_app(self) -> None:
        """Switch to the next app."""
        await self._publish("nextapp")

    async def previous_app(self) -> None:
        """Switch to the previous app."""
        await self._publish("previousapp")

    async def switch_app(self, name: str) -> None:
        """Switch to a specific app by name."""
        await self._publish("switch", json.dumps({"name": name}))

    async def update_settings(self, settings: dict) -> None:
        """Update device settings."""
        await self._publish("settings", json.dumps(settings))

    async def sleep(self, seconds: int) -> None:
        """Put the device to sleep."""
        await self._publish("sleep", json.dumps({"sleep": seconds}))

    async def reboot(self) -> None:
        """Reboot the device."""
        await self._publish("reboot")

    async def get_screen(self) -> bytes:
        """Not available via MQTT; returns empty bytes."""
        return b""

    async def ensure_icons(self, icon_ids: list[int]) -> None:
        pass
