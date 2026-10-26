"""Sensor platform for Salus iT600 Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SalusCloudCoordinator, SalusDevice
from .devices import is_climate_device
from .entity import SalusEntity, async_add_salus_entities
from .heating import (
    COOLING_SETPOINT_METRIC,
    DIAGNOSTIC_METRICS,
    HUMIDITY_METRIC,
    TEMPERATURE_METRICS,
    DiagnosticKind,
    DiagnosticMetric,
    HumidityMetric,
    TemperatureMetric,
    diagnostics,
    observe,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus iT600 Cloud sensors."""
    coordinator: SalusCloudCoordinator = entry.runtime_data

    def records() -> dict[str, SalusDevice]:
        data = coordinator.data or {}
        return {
            device_id: device
            for device_id, device in data.items()
            if is_climate_device(device) or _has_temperature(device)
        }

    def entities(device_id: str, device: SalusDevice) -> list[SensorEntity]:
        if is_climate_device(device):
            return [SalusHeatingTemperature(coordinator, device_id, device, metric) for metric in TEMPERATURE_METRICS]
        return [SalusCloudTemperatureSensor(coordinator, device_id, device)]

    async_add_salus_entities(entry, coordinator, async_add_entities, records, entities)
    _add_shown_temperature(entry, coordinator, async_add_entities, COOLING_SETPOINT_METRIC)
    _add_humidity(entry, coordinator, async_add_entities, HUMIDITY_METRIC)
    for metric in DIAGNOSTIC_METRICS:
        _add_diagnostic(entry, coordinator, async_add_entities, metric)


def _add_diagnostic(
    entry: ConfigEntry,
    coordinator: SalusCloudCoordinator,
    async_add_entities: AddEntitiesCallback,
    metric: DiagnosticMetric,
) -> None:
    """Discover one diagnostic on its own seen set, so a cell can show up after the thermostat."""

    def records() -> dict[str, SalusDevice]:
        data = coordinator.data or {}
        selected: dict[str, SalusDevice] = {}
        for device_id, device in data.items():
            if not is_climate_device(device):
                continue
            reading = diagnostics(device.get("_shadow_properties") or {})
            if reading is not None and metric.read(reading).present:
                selected[device_id] = device
        return selected

    def entities(device_id: str, device: SalusDevice) -> list[SalusDiagnosticSensor]:
        return [SalusDiagnosticSensor(coordinator, device_id, device, metric)]

    async_add_salus_entities(entry, coordinator, async_add_entities, records, entities)


def _add_shown_temperature(
    entry: ConfigEntry,
    coordinator: SalusCloudCoordinator,
    async_add_entities: AddEntitiesCallback,
    metric: TemperatureMetric,
) -> None:
    """Discover one setpoint on its own seen set, so the cell can show up after the thermostat."""

    def records() -> dict[str, SalusDevice]:
        data = coordinator.data or {}
        selected: dict[str, SalusDevice] = {}
        for device_id, device in data.items():
            if not is_climate_device(device):
                continue
            observation = observe(device.get("_shadow_properties") or {})
            if observation is not None and metric.shown is not None and metric.shown(observation):
                selected[device_id] = device
        return selected

    def entities(device_id: str, device: SalusDevice) -> list[SalusHeatingTemperature]:
        return [SalusHeatingTemperature(coordinator, device_id, device, metric)]

    async_add_salus_entities(entry, coordinator, async_add_entities, records, entities)


def _add_humidity(
    entry: ConfigEntry,
    coordinator: SalusCloudCoordinator,
    async_add_entities: AddEntitiesCallback,
    metric: HumidityMetric,
) -> None:
    """Discover humidity on its own seen set, so the cell can show up after the thermostat."""

    def records() -> dict[str, SalusDevice]:
        data = coordinator.data or {}
        selected: dict[str, SalusDevice] = {}
        for device_id, device in data.items():
            if not is_climate_device(device):
                continue
            observation = observe(device.get("_shadow_properties") or {})
            if observation is not None and metric.shown(observation):
                selected[device_id] = device
        return selected

    def entities(device_id: str, device: SalusDevice) -> list[SalusHumidity]:
        return [SalusHumidity(coordinator, device_id, device, metric)]

    async_add_salus_entities(entry, coordinator, async_add_entities, records, entities)


def _has_temperature(device: dict[str, Any]) -> bool:
    """Check if device is a standalone temperature sensor."""
    device_type = device.get("type", "").lower()
    return device_type == "temperature_sensor" or (device_type == "sensor" and "temperature" in device)


def _value(data: dict[str, Any], fields: tuple[str, ...], scale_above_100: bool) -> float | None:
    """Return first present field from device data or its status, scaled from x100 format when needed."""
    for source in (data, data.get("status") if isinstance(data.get("status"), dict) else {}):
        for field in fields:
            if field in source:
                value = source[field]
                if scale_above_100 and isinstance(value, int) and value > 100:
                    return value / 100.0
                return float(value)
    return None


class SalusHeatingTemperature(SalusEntity, SensorEntity):
    """Room temperature or a setpoint from the thermostat shadow."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device: SalusDevice,
        metric: TemperatureMetric,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, device)
        self._metric = metric
        self._attr_name = f"{self._attr_name} {metric.name}"
        self._attr_unique_id = f"{self._attr_unique_id}_{metric.slug}"
        self._attr_translation_key = metric.translation_key

    @property
    def native_value(self) -> float | None:
        """Return the temperature in degrees Celsius."""
        observation = observe(self.shadow_properties)
        sample = None if observation is None else self._metric.read(observation)
        return None if sample is None else sample.celsius()


class SalusHumidity(SalusEntity, SensorEntity):
    """Relative humidity from the thermostat shadow."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device: SalusDevice,
        metric: HumidityMetric,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, device)
        self._metric = metric
        self._attr_name = f"{self._attr_name} {metric.name}"
        self._attr_unique_id = f"{self._attr_unique_id}_{metric.slug}"
        self._attr_translation_key = metric.translation_key

    @property
    def native_value(self) -> float | None:
        """Return relative humidity in percent."""
        observation = observe(self.shadow_properties)
        sample = None if observation is None else self._metric.read(observation)
        return None if sample is None else sample.percent()


class SalusDiagnosticSensor(SalusEntity, SensorEntity):
    """Battery level, signal strength, or link quality from the thermostat shadow."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device: SalusDevice,
        metric: DiagnosticMetric,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator, device_id, device)
        self._metric = metric
        self._attr_name = f"{self._attr_name} {metric.name}"
        self._attr_unique_id = f"{self._attr_unique_id}_{metric.slug}"
        self._attr_translation_key = metric.translation_key
        if metric.kind is DiagnosticKind.SIGNAL_DBM:
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT

    @property
    def native_value(self) -> int | None:
        """Return the raw integer. None when the cell is absent or not an int."""
        reading = diagnostics(self.shadow_properties)
        if reading is None:
            return None
        return self._metric.read(reading).value


class SalusCloudSensor(SalusEntity, SensorEntity):
    """Base class for Salus Cloud sensors."""

    def __init__(
        self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice, sensor_type: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, device)
        self._attr_name = f"{self._attr_name} {sensor_type.title()}"
        self._attr_unique_id = f"{self._attr_unique_id}_{sensor_type}"


class SalusCloudTemperatureSensor(SalusCloudSensor):
    """Temperature sensor for Salus Cloud devices."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    _attr_translation_key = "temperature"

    def __init__(self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator, device_id, device, "temperature")

    @property
    def native_value(self) -> float | None:
        """Return the temperature value."""
        return _value(self.device_data, ("temperature", "current_temperature", "LocalTemperature"), True)
