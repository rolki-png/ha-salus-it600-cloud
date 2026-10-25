"""Tests for the thermostat running-state binary sensor."""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.climate import HVACAction
from homeassistant.const import EntityCategory

from custom_components.salus_it600_cloud import binary_sensor
from custom_components.salus_it600_cloud.binary_sensor import (
    SalusCloudBinarySensor,
    SalusRunningState,
    SalusThermostatProblem,
)
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
    assert entity.unique_id == _uid(fixtures.THERMOSTAT_ID)
    assert entity.has_entity_name is False
    assert entity.translation_key == "running_state"


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


def _contact(device_id: str, **fields: object) -> dict[str, object]:
    return {
        "id": device_id,
        "name": device_id,
        "_gateway_id": fixtures.GATEWAY_ID,
        "_fresh": True,
        **fields,
    }


def _contact_uid(device_id: str) -> str:
    return f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{device_id}"


async def _setup_contacts(coordinator: object) -> dict[str, object]:
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    await binary_sensor.async_setup_entry(MagicMock(), entry, add_entities)
    return {entity.unique_id: entity for entity in add_entities.call_args.args[0]}


async def test_wls_is_moisture_and_window_and_door_keep_their_classes() -> None:
    """A WLS model is moisture. Window and door come from the model or the type."""

    coordinator, _, _ = await create_coordinator()
    coordinator.data["leak"] = _contact("leak", type="door_sensor", model="WLS600")
    coordinator.data["window"] = _contact("window", type="window_sensor", model="SW600")
    coordinator.data["door"] = _contact("door", type="door_sensor", model="OS600")
    coordinator.data["hall"] = _contact("hall", type="binary_sensor", model="Hall Window")

    entities = await _setup_contacts(coordinator)

    assert entities[_contact_uid("leak")].device_class is BinarySensorDeviceClass.MOISTURE
    assert entities[_contact_uid("window")].device_class is BinarySensorDeviceClass.WINDOW
    assert entities[_contact_uid("door")].device_class is BinarySensorDeviceClass.DOOR
    assert entities[_contact_uid("hall")].device_class is BinarySensorDeviceClass.WINDOW


async def test_contact_without_a_state_field_is_unknown() -> None:
    """No matching field leaves the contact unknown, and the entity stays available."""

    coordinator, _, _ = await create_coordinator()
    coordinator.data["leak"] = _contact("leak", type="binary_sensor", model="WLS600")

    entities = await _setup_contacts(coordinator)
    entity = entities[_contact_uid("leak")]

    assert entity.is_on is None
    assert entity.available is True


async def test_reported_open_and_closed_values() -> None:
    """A present open field still reports on and off."""

    coordinator, _, _ = await create_coordinator()
    coordinator.data["open"] = _contact("open", type="door_sensor", model="OS600", open=1)
    coordinator.data["shut"] = _contact("shut", type="door_sensor", model="OS600", open=0)

    entities = await _setup_contacts(coordinator)

    assert entities[_contact_uid("open")].is_on is True
    assert entities[_contact_uid("shut")].is_on is False


ERROR_01 = "ep9:sIT600TH:Error01"
ERROR_06 = "ep9:sIT600TH:Error06"
ERROR_32 = "ep9:sIT600TH:Error32"


async def _thermostat_with(**properties: object):
    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=0)
    shadow["state"]["reported"]["11"]["properties"].update(properties)
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    return await create_coordinator(api)


def _problem_uid(device_id: str = fixtures.THERMOSTAT_ID) -> str:
    return f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{device_id}_problem"


async def test_error_codes_become_one_problem_sensor() -> None:
    """Integer 1 is a problem. The attribute lists those codes and skips zeros, bools, and other clusters."""

    coordinator, _, _ = await _thermostat_with(
        **{
            ERROR_01: 0,
            ERROR_06: 1,
            ERROR_32: 1,
            "ep9:sIT600TH:Error09": True,
            "ep8:sIT600WC:Error10": 1,
        }
    )
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    await binary_sensor.async_setup_entry(MagicMock(), entry, add_entities)
    entities = {
        entity.unique_id: entity
        for call in add_entities.call_args_list
        for entity in call.args[0]
    }
    entity = entities[_problem_uid()]

    assert isinstance(entity, SalusThermostatProblem)
    assert not isinstance(entity, SalusCloudBinarySensor)
    assert entity.device_class is BinarySensorDeviceClass.PROBLEM
    assert entity.entity_category is EntityCategory.DIAGNOSTIC
    assert entity.is_on is True
    assert entity.extra_state_attributes == {"error_codes": ["Error06", "Error32"]}
    assert entity.name == "Apartmán A Termostat pokoj Problem"
    assert entity.translation_key == "problem"
    assert entity.has_entity_name is False
    assert _problem_uid(fixtures.THERMOSTAT_2_ID) not in entities
    assert _uid(fixtures.THERMOSTAT_ID) in entities


async def test_reported_zeros_are_off_and_list_no_codes() -> None:
    coordinator, _, _ = await _thermostat_with(**{ERROR_01: 0})
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    await binary_sensor.async_setup_entry(MagicMock(), entry, add_entities)
    entity = next(item for item in add_entities.call_args.args[0] if item.unique_id == _problem_uid())

    assert entity.is_on is False
    assert entity.extra_state_attributes == {"error_codes": []}


async def test_problem_is_unknown_when_every_error_key_leaves() -> None:
    """No Error keys at all is unknown, not off."""

    coordinator, _, _ = await _thermostat_with(**{ERROR_01: 1})
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    await binary_sensor.async_setup_entry(MagicMock(), entry, add_entities)
    entity = next(item for item in add_entities.call_args.args[0] if item.unique_id == _problem_uid())
    entity.hass = MagicMock()
    del coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"][ERROR_01]

    assert entity.is_on is None
    assert entity.extra_state_attributes == {}
    assert entity.available is True


async def test_error_key_that_appears_later_creates_the_problem_sensor() -> None:
    """Running state can already exist. The problem sensor still appears when the first error key does."""

    coordinator, _, _ = await create_coordinator()
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    await binary_sensor.async_setup_entry(MagicMock(), entry, add_entities)
    assert _problem_uid() not in [entity.unique_id for call in add_entities.call_args_list for entity in call.args[0]]

    properties = dict(coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"])
    properties[ERROR_01] = 1
    coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"] = properties
    coordinator.async_set_updated_data(dict(coordinator.data))
    entity = next(
        entity
        for call in add_entities.call_args_list
        for entity in call.args[0]
        if entity.unique_id == _problem_uid()
    )

    assert entity.is_on is True
    assert entity.extra_state_attributes == {"error_codes": ["Error01"]}


async def test_a_wiring_centre_error_does_not_create_the_problem_sensor() -> None:
    coordinator, _, _ = await _thermostat_with(**{"ep8:sIT600WC:Error10": 1})
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    await binary_sensor.async_setup_entry(MagicMock(), entry, add_entities)
    unique_ids = [entity.unique_id for entity in add_entities.call_args.args[0]]

    assert _problem_uid() not in unique_ids
