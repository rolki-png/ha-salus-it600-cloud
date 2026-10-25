"""Lock platform for Salus iT600 Cloud thermostat keypads."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SalusCloudCoordinator, SalusDevice
from .devices import is_climate_device
from .entity import SalusEntity, async_add_salus_entities
from .heating import LOCK_METRIC, diagnostics


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up keypad locks for thermostats that report LockKey."""
    coordinator: SalusCloudCoordinator = entry.runtime_data

    def records() -> dict[str, SalusDevice]:
        data = coordinator.data or {}
        selected: dict[str, SalusDevice] = {}
        for device_id, device in data.items():
            if not is_climate_device(device):
                continue
            reading = diagnostics(device.get("_shadow_properties") or {})
            if reading is not None and reading.lock.cell.present:
                selected[device_id] = device
        return selected

    def entities(device_id: str, device: SalusDevice) -> list[SalusThermostatLock]:
        return [SalusThermostatLock(coordinator, device_id, device)]

    async_add_salus_entities(entry, coordinator, async_add_entities, records, entities)


class SalusThermostatLock(SalusEntity, LockEntity):
    """Thermostat keypad lock."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SalusCloudCoordinator, device_id: str, device: SalusDevice) -> None:
        """Initialize the lock."""
        super().__init__(coordinator, device_id, device)
        self._attr_name = f"{self._attr_name} {LOCK_METRIC.name}"
        self._attr_unique_id = f"{self._attr_unique_id}_{LOCK_METRIC.slug}"

    @property
    def is_locked(self) -> bool | None:
        """Return whether the keypad is locked. None unless LockKey is 0 or 1."""
        reading = diagnostics(self.shadow_properties)
        return None if reading is None else reading.lock.is_locked()

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the keypad."""
        await self.coordinator.async_set_lock(self._device_id, True)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the keypad."""
        await self.coordinator.async_set_lock(self._device_id, False)
