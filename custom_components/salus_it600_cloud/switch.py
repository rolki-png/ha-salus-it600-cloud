"""Switch platform for Salus iT600 Cloud relays and smart plugs."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SalusCloudCoordinator, SalusDevice
from .devices import is_switch_device
from .entity import SalusEntity, async_add_salus_entities

ON_OFF = "ep9:sOnOffS:OnOff"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus iT600 Cloud relays and smart plugs."""
    coordinator: SalusCloudCoordinator = entry.runtime_data

    def records() -> dict[str, SalusDevice]:
        data = coordinator.data or {}
        return {device_id: device for device_id, device in data.items() if is_switch_device(device)}

    def entities(device_id: str, device: SalusDevice) -> list[SalusCloudSwitch]:
        return [SalusCloudSwitch(coordinator, device_id, device)]

    async_add_salus_entities(entry, coordinator, async_add_entities, records, entities)


class SalusCloudSwitch(SalusEntity, SwitchEntity):
    """Salus relay or smart plug."""

    @property
    def is_on(self) -> bool | None:
        """Return whether the relay is on."""
        value = self.shadow_properties.get(ON_OFF)
        return value == 1 if value is not None else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the relay on."""
        await self.coordinator.async_set_switch(self._device_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the relay off."""
        await self.coordinator.async_set_switch(self._device_id, False)
