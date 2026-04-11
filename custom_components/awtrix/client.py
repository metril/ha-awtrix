"""AWTRIX client abstraction layer."""

from __future__ import annotations

from abc import ABC, abstractmethod

import aiohttp

from .models import AwtrixStats


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
    async def set_moodlight(self, payload: dict) -> None:
        """Set mood light configuration."""

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
    ) -> None:
        """Initialise the HTTP client."""
        self._session = session
        self._base_url = f"http://{host}:{port}/api"
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _request(self, method: str, path: str, **kwargs) -> _AwtrixResponse:
        """Perform an HTTP request and fully consume the response body.

        Raises:
            AwtrixConnectionError: if the device cannot be reached.
            AwtrixApiError: if the response status is not 200.
        """
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method, url, timeout=self._timeout, **kwargs
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

    async def set_moodlight(self, payload: dict) -> None:
        """POST /api/moodlight with the moodlight payload."""
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
