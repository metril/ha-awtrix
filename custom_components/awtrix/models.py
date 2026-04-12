"""Data models for the AWTRIX 3 integration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AwtrixStats:
    """Device statistics from /api/stats."""

    uid: str = ""
    battery: int = 0
    battery_raw: int = 0
    lux: int = 0
    ldr_raw: int = 0
    ram: int = 0
    brightness: int = 0
    temperature: float = 0.0
    humidity: float = 0.0
    uptime: int = 0
    wifi_signal: int = 0
    firmware: str = ""
    ip_address: str = ""
    current_app: str = ""
    indicator1: bool = False
    indicator2: bool = False
    indicator3: bool = False
    matrix: bool = True
    messages: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> AwtrixStats:
        """Create from AWTRIX API response dict.

        Field names match the AWTRIX3 firmware (DisplayManager::getStats).
        """
        return cls(
            uid=data.get("uid", ""),
            battery=data.get("bat", 0),
            battery_raw=data.get("batRaw", 0),
            lux=data.get("lux", 0),
            ldr_raw=data.get("ldrRaw", 0),
            ram=data.get("ram", 0),
            brightness=data.get("bri", 0),
            temperature=data.get("temp", 0.0),
            humidity=data.get("hum", 0.0),
            uptime=data.get("uptime", 0),
            wifi_signal=data.get("sig", 0),
            firmware=data.get("ver", ""),
            ip_address=data.get("ip", ""),
            current_app=data.get("app", ""),
            indicator1=data.get("indicator1", False),
            indicator2=data.get("indicator2", False),
            indicator3=data.get("indicator3", False),
            matrix=data.get("matrix", True),
            messages=data.get("messages", 0),
        )


@dataclass
class AwtrixDeviceData:
    """Complete device state held by the coordinator."""

    stats: AwtrixStats = field(default_factory=AwtrixStats)
    settings: dict = field(default_factory=dict)
    effects: list[str] = field(default_factory=list)
    transitions: list[str] = field(default_factory=list)
    connected: bool = False
