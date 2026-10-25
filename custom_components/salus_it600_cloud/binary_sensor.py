"""Binary sensor platform for Salus iT600 Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SalusCloudCoordinator, SalusDevice
from .devices import is_climate_device
from .entity import SalusEntity, async_add_salus_entities
from .heating import PROBLEM_METRIC, RUNNING_STATE_METRIC, diagnostics, observe

BINARY_SENSOR_TYPES = ("door_sensor", "window_sensor", "motion_sensor", "binary_sensor")
TRUE_VALUES = ("on", "true", "1", "open", "active")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus iT600 Cloud binary sensors."""
    coordinator: SalusCloudCoordinator = entry.runtime_data

    def records() -> dict[str, SalusDevice]:
        data = coordinator.data or {}
        return {
            device_id: device
            for device_id, device in data.items()
            if _is_binary_sensor_device(device) or is_climate_device(device)
        }

    def entities(device_id: str, device: SalusDevice) -> list[BinarySensorEntity]:
        created: list[BinarySensorEntity] = []
        if _is_binary_sensor_device(device):
            created.append(SalusCloudBinarySensor(coordinator, device_id, device, _get_device_class(device)))
        if is_climate_device(device):
            created.append(SalusRunningState(coordinator, device_id, device))
        return created

    async_add_salus_entities(entry, coordinator, async_add_entities, records, entities)

    def problem_records() -> dict[str, SalusDevice]:
        data = coordinator.data or {}
        selected: dict[str, SalusDevice] = {}
        for device_id, device in data.items():
            if not is_climate_device(device):
                continue
            reading = diagnostics(device.get("_shadow_properties") or {})
            if reading is not None and reading.errors.known:
                selected[device_id] = device
        return selected

    def problem_entities(device_id: str, device: SalusDevice) -> list[SalusThermostatProblem]:
        return [SalusThermostatProblem(coordinator, device_id, device)]

    async_add_salus_entities(entry, coordinator, async_add_entities, problem_records, problem_entities)


def _is_binary_sensor_device(device: dict[str, Any]) -> bool:
    """Determine if device is a binary sensor."""
    return device.get("type", "").lower() in BINARY_SENSOR_TYPES or device.get("model", "").upper().startswith("WLS")


def _get_device_class(device: dict[str, Any]) -> BinarySensorDeviceClass | None:
    """Determine binary sensor device class."""
    device_type = (device.get("type") or "").lower()
    model = (device.get("model") or "").upper()
    if model.startswith("WLS"):
        return BinarySensorDeviceClass.MOISTURE
    if "window" in device_type or "WINDOW" in model:
        return BinarySensorDeviceClass.WINDOW
    if "door" in device_type or "DOOR" in model:
        return BinarySensorDeviceClass.DOOR
    if "motion" in device_type:
        return BinarySensorDeviceClass.MOTION
    if "occupancy" in device_type:
        return BinarySensorDeviceClass.OCCUPANCY
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in TRUE_VALUES
    if isinstance(value, int):
        return value == 1
    return None


class SalusRunningState(SalusEntity, BinarySensorEntity):
    """Call for heat from RunningState.

    This can be on while climate hvac_action is off, because frost protection still reports demand.
    """

    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice) -> None:
        """Initialize the running-state sensor."""
        super().__init__(coordinator, device_id, device)
        self._attr_name = f"{self._attr_name} {RUNNING_STATE_METRIC.name}"
        self._attr_unique_id = f"{self._attr_unique_id}_{RUNNING_STATE_METRIC.slug}"

    @property
    def is_on(self) -> bool | None:
        """Return whether the thermostat is calling for heat. None when that was not reported as an int."""
        observation = observe(self.shadow_properties)
        return None if observation is None else observation.demand.is_on()


class SalusThermostatProblem(SalusEntity, BinarySensorEntity):
    """One problem sensor for every reported Error01..Error32 cell."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice) -> None:
        """Initialize the problem sensor."""
        super().__init__(coordinator, device_id, device)
        self._attr_name = f"{self._attr_name} {PROBLEM_METRIC.name}"
        self._attr_unique_id = f"{self._attr_unique_id}_{PROBLEM_METRIC.slug}"

    @property
    def is_on(self) -> bool | None:
        """True when any error code is the integer 1. None when no error keys remain."""
        reading = diagnostics(self.shadow_properties)
        return None if reading is None else reading.errors.is_on()

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        """Active error codes. Omitted when the thermostat has reported no error keys."""
        reading = diagnostics(self.shadow_properties)
        if reading is None or not reading.errors.known:
            return {}
        return {"error_codes": list(reading.errors.active)}


class SalusCloudBinarySensor(SalusEntity, BinarySensorEntity):
    """Salus iT600 Cloud binary sensor."""

    def __init__(
        self,
        coordinator: SalusCloudCoordinator,
        device_id: str,
        device: SalusDevice,
        device_class: BinarySensorDeviceClass | None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, device_id, device)
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool | None:
        """Return whether the contact is on. None when no field reports it."""
        data = self.device_data
        for field in ("is_on", "state", "active", "triggered", "open"):
            if field in data and (value := _as_bool(data[field])) is not None:
                return value
        status = data.get("status")
        if isinstance(status, dict):
            for field in ("state", "active", "triggered"):
                if field in status and (value := _as_bool(status[field])) is not None:
                    return value
        return None
