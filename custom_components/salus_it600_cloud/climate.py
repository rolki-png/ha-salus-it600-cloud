"""Climate platform for Salus iT600 Cloud thermostats."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SalusCloudCoordinator, SalusDevice
from .devices import is_climate_device
from .entity import SalusEntity, async_add_salus_entities
from .heating import PRESET_SLUGS, CentiCelsius, HeatingAction, heating_action, hold_raw_for_preset, observe


def _degrees(sample: CentiCelsius | None, default: float) -> float:
    """Return degrees from a reported sample, or the default when that sample is absent."""
    if sample is None:
        return default
    return sample.celsius()


# Each slider step calls set_temperature. Wait out the burst, then send the last value.
TARGET_TEMPERATURE_DEBOUNCE_SECONDS = 0.3

_HVAC_ACTION: dict[HeatingAction, HVACAction | None] = {
    HeatingAction.HEATING: HVACAction.HEATING,
    HeatingAction.IDLE: HVACAction.IDLE,
    HeatingAction.OFF: HVACAction.OFF,
    HeatingAction.UNKNOWN: None,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Salus iT600 Cloud thermostats."""
    coordinator: SalusCloudCoordinator = entry.runtime_data

    def records() -> dict[str, SalusDevice]:
        data = coordinator.data or {}
        return {device_id: device for device_id, device in data.items() if is_climate_device(device)}

    def entities(device_id: str, device: SalusDevice) -> list[SalusCloudClimate]:
        return [SalusCloudClimate(coordinator, device_id, device)]

    async_add_salus_entities(entry, coordinator, async_add_entities, records, entities)


class SalusCloudClimate(SalusEntity, ClimateEntity):
    """Salus iT600 thermostat."""

    _attr_translation_key = "thermostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = list(PRESET_SLUGS)
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0
    _temperature_write: asyncio.Task[None] | None = None

    @property
    def min_temp(self) -> float:
        """Return the lowest heating setpoint the shadow reports, or 5°C."""
        observation = observe(self.shadow_properties)
        sample = None if observation is None else observation.min_heat_setpoint
        return _degrees(sample, self._attr_min_temp)

    @property
    def max_temp(self) -> float:
        """Return the highest heating setpoint the shadow reports, or 35°C."""
        observation = observe(self.shadow_properties)
        sample = None if observation is None else observation.max_heat_setpoint
        return _degrees(sample, self._attr_max_temp)

    @property
    def current_temperature(self) -> float | None:
        """Return the measured temperature."""
        observation = observe(self.shadow_properties)
        sample = None if observation is None else observation.local_temperature
        return None if sample is None else sample.celsius()

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        observation = observe(self.shadow_properties)
        sample = None if observation is None else observation.heating_setpoint
        return None if sample is None else sample.celsius()

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return off for stand-by or system mode off, heat otherwise."""
        observation = observe(self.shadow_properties)
        if observation is None:
            return None
        if observation.hold.is_standby or observation.system_mode.is_off:
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return whether the thermostat is heating. Unknown when demand was not an integer."""
        return _HVAC_ACTION[heating_action(observe(self.shadow_properties))]

    @property
    def preset_mode(self) -> str | None:
        """Return preset matching the hold type."""
        observation = observe(self.shadow_properties)
        return None if observation is None else observation.preset_slug()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature. A newer setpoint cancels a write that has not been sent."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        self._cancel_pending_temperature_write()
        write = asyncio.create_task(self._async_write_temperature(float(temperature)))
        self._temperature_write = write
        try:
            await write
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise

    async def _async_write_temperature(self, temperature: float) -> None:
        await asyncio.sleep(TARGET_TEMPERATURE_DEBOUNCE_SECONDS)
        await self.coordinator.async_set_temperature(self._device_id, temperature)

    def _cancel_pending_temperature_write(self) -> None:
        write = self._temperature_write
        if write is not None and not write.done():
            write.cancel()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset (synchronized across the gateway when enabled)."""
        await self.coordinator.async_set_hold_type(self._device_id, hold_raw_for_preset(preset_mode))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set off (stand-by) or heat (follow schedule), synchronized across the gateway when enabled."""
        slug = "away" if hvac_mode == HVACMode.OFF else "schedule"
        await self.coordinator.async_set_hold_type(self._device_id, hold_raw_for_preset(slug))

    async def async_turn_on(self) -> None:
        """Turn heating on (follow schedule)."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn heating off (stand-by)."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return hold type, system mode, battery voltage and running state."""
        observation = observe(self.shadow_properties)
        if observation is None:
            return {}
        attributes: dict[str, Any] = {}
        if (hold_type := observation.hold_label()) is not None:
            attributes["hold_type"] = hold_type
        if (system_mode := observation.system_mode_label()) is not None:
            attributes["system_mode"] = system_mode
        if observation.battery is not None:
            attributes["battery_voltage"] = f"{observation.battery.volts():.1f}V"
        if (running_state := observation.demand.attribute_label()) is not None:
            attributes["running_state"] = running_state
        return attributes
