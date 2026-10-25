"""Binary sensor platform for Salus iT600 Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SalusCloudCoordinator, SalusDevice
from .devices import is_climate_device
from .entity import SalusEntity, async_add_salus_entities
from .heating import RUNNING_STATE_METRIC, observe

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
