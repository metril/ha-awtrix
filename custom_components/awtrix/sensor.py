"""Sensor platform for AWTRIX 3 integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AwtrixCoordinator
from .entity import AwtrixEntity
from .models import AwtrixDeviceData


@dataclass(frozen=True, kw_only=True)
class AwtrixSensorDescription(SensorEntityDescription):
    """Describes an AWTRIX sensor entity."""

    value_fn: Callable[[AwtrixDeviceData], Any] = lambda data: None


SENSORS: tuple[AwtrixSensorDescription, ...] = (
    AwtrixSensorDescription(
        key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.stats.temperature,
    ),
    AwtrixSensorDescription(
        key="humidity",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.stats.humidity,
    ),
    AwtrixSensorDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.stats.battery,
    ),
    AwtrixSensorDescription(
        key="illuminance",
        name="Illuminance",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement="lx",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.stats.lux,
    ),
    AwtrixSensorDescription(
        key="wifi_signal",
        name="WiFi Signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.stats.wifi_signal,
    ),
    AwtrixSensorDescription(
        key="ram",
        name="Free RAM",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.stats.ram,
    ),
    AwtrixSensorDescription(
        key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.stats.uptime,
    ),
    AwtrixSensorDescription(
        key="firmware",
        name="Firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.stats.firmware,
    ),
    AwtrixSensorDescription(
        key="current_app",
        name="Current App",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.stats.current_app,
    ),
    AwtrixSensorDescription(
        key="ip_address",
        name="IP Address",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.stats.ip_address,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AWTRIX sensor entities from a config entry."""
    coordinator: AwtrixCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        AwtrixSensor(coordinator, entry, description) for description in SENSORS
    )


class AwtrixSensor(AwtrixEntity, SensorEntity):
    """Represents an AWTRIX sensor entity."""

    entity_description: AwtrixSensorDescription

    def __init__(
        self,
        coordinator: AwtrixCoordinator,
        entry: ConfigEntry,
        description: AwtrixSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = (
            f"{entry.unique_id or entry.entry_id}_{description.key}"
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
