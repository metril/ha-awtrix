"""Base entity for AWTRIX 3 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_HOST, CONF_PORT, CONF_CONNECTION_TYPE, CONNECTION_HTTP
from .coordinator import AwtrixCoordinator


class AwtrixEntity(CoordinatorEntity[AwtrixCoordinator]):
    """Base entity for all AWTRIX entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AwtrixCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)

        configuration_url = None
        if entry.data.get(CONF_CONNECTION_TYPE) == CONNECTION_HTTP:
            host = entry.data.get(CONF_HOST, "")
            port = entry.data.get(CONF_PORT, 80)
            configuration_url = f"http://{host}:{port}"

        sw_version = None
        if coordinator.data and coordinator.data.stats:
            sw_version = coordinator.data.stats.firmware

        uid = entry.unique_id or entry.entry_id

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name=entry.title,
            manufacturer="Blueforcer",
            model="AWTRIX 3",
            sw_version=sw_version,
            configuration_url=configuration_url,
        )
