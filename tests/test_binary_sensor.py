"""Tests for the thermostat running-state binary sensor."""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.climate import HVACAction

from custom_components.salus_it600_cloud import binary_sensor
from custom_components.salus_it600_cloud.binary_sensor import SalusCloudBinarySensor, SalusRunningState
from custom_components.salus_it600_cloud.climate import SalusCloudClimate

from . import fixtures
from .helpers import FakeApi, create_coordinator


def _entity(coordinator: object, device_id: str = fixtures.THERMOSTAT_ID) -> SalusRunningState:
    entity = SalusRunningState(coordinator, device_id, coordinator.data[device_id])
    entity.hass = MagicMock()
    return entity


def _uid(device_id: str) -> str:
    return f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{device_id}_running_state"


async def test_setup_creates_one_heat_sensor_per_thermostat() -> None:
    """Running state is its own entity. It does not use the on/off fallback of other binary sensors."""

    coordinator, _, _ = await create_coordinator()
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()

    await binary_sensor.async_setup_entry(MagicMock(), entry, add_entities)

    entities = add_entities.call_args.args[0]
    assert [entity.unique_id for entity in entities] == [
        _uid(fixtures.THERMOSTAT_ID),
        _uid(fixtures.THERMOSTAT_2_ID),
    ]
    assert all(type(entity) is SalusRunningState for entity in entities)
    assert all(not isinstance(entity, SalusCloudBinarySensor) for entity in entities)
    assert all(entity.device_class is BinarySensorDeviceClass.HEAT for entity in entities)


async def test_idle_demand_is_off() -> None:
    coordinator, _, _ = await create_coordinator()
    entity = _entity(coordinator)

    assert entity.is_on is False
    assert entity.available is True
    assert entity.name == "Apartmán A Termostat pokoj Running state"


async def test_missing_running_state_is_unknown_not_off() -> None:
    """A fresh thermostat with no RunningState key is unknown, not off and not unavailable."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=0)
    del shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:RunningState"]
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert entity.is_on is None
    assert entity.available is True


async def test_integer_one_is_on() -> None:
    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=2)
    shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:RunningState"] = 1
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)

    assert _entity(coordinator).is_on is True


async def test_bool_running_state_is_unknown() -> None:
    """True must not become on, because True == 1."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=2)
    shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:RunningState"] = True
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)

    assert _entity(coordinator).is_on is None


async def test_unavailable_follows_freshness_not_the_key() -> None:
    api = FakeApi()
    del api.shadows[fixtures.THERMOSTAT_CODE]
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert entity.available is False
    assert entity.is_on is None


async def test_calling_during_standby_is_on_while_climate_action_is_off() -> None:
    """Frost protection can still be calling for heat. Climate reports that as off."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=7)
    shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:RunningState"] = 1
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)
    climate = SalusCloudClimate(coordinator, fixtures.THERMOSTAT_ID, coordinator.data[fixtures.THERMOSTAT_ID])
    climate.hass = MagicMock()

    assert _entity(coordinator).is_on is True
    assert climate.hvac_action is HVACAction.OFF
