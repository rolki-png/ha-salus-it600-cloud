"""Tests for thermostat temperature sensors."""

from unittest.mock import MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, UnitOfTemperature

from custom_components.salus_it600_cloud import sensor
from custom_components.salus_it600_cloud.heating import TEMPERATURE_METRICS
from custom_components.salus_it600_cloud.sensor import SalusDiagnosticSensor, SalusHeatingTemperature

from . import fixtures
from .helpers import CALL_LATER, FakeApi, create_coordinator


def _metric(slug: str):
    return next(metric for metric in TEMPERATURE_METRICS if metric.slug == slug)


def _entity(coordinator: object, slug: str, device_id: str = fixtures.THERMOSTAT_ID) -> SalusHeatingTemperature:
    entity = SalusHeatingTemperature(coordinator, device_id, coordinator.data[device_id], _metric(slug))
    entity.hass = MagicMock()
    return entity


def _uid(device_id: str, slug: str) -> str:
    return f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{device_id}_{slug}"


async def test_setup_creates_measurement_sensors_for_thermostats_only() -> None:
    """Each thermostat gets a temperature and a setpoint sensor. Relays do not."""

    coordinator, _, _ = await create_coordinator()
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()

    await sensor.async_setup_entry(MagicMock(), entry, add_entities)

    entities = add_entities.call_args.args[0]
    assert [entity.unique_id for entity in entities] == [
        _uid(fixtures.THERMOSTAT_ID, "local_temperature"),
        _uid(fixtures.THERMOSTAT_ID, "heating_setpoint"),
        _uid(fixtures.THERMOSTAT_2_ID, "local_temperature"),
        _uid(fixtures.THERMOSTAT_2_ID, "heating_setpoint"),
    ]
    assert all(entity.state_class is SensorStateClass.MEASUREMENT for entity in entities)
    assert all(entity.device_class is SensorDeviceClass.TEMPERATURE for entity in entities)
    assert all(entity.native_unit_of_measurement == UnitOfTemperature.CELSIUS for entity in entities)
    assert all(entity.suggested_display_precision == 1 for entity in entities)


async def test_native_values_match_reported_temperatures() -> None:
    """The sensors show the same degrees the climate entity shows."""

    coordinator, _, _ = await create_coordinator()

    room = _entity(coordinator, "local_temperature")
    setpoint = _entity(coordinator, "heating_setpoint")

    assert room.native_value == 22.0
    assert setpoint.native_value == 21.0
    assert room.name == "Apartmán A Termostat pokoj Temperature"
    assert setpoint.name == "Apartmán A Termostat pokoj Heating setpoint"
    assert room.unique_id == _uid(fixtures.THERMOSTAT_ID, "local_temperature")
    assert setpoint.unique_id == _uid(fixtures.THERMOSTAT_ID, "heating_setpoint")
    assert room.has_entity_name is False
    assert setpoint.has_entity_name is False
    assert room.translation_key == "temperature"
    assert setpoint.translation_key == "heating_setpoint"


async def test_missing_temperature_is_unknown_and_the_entity_still_exists() -> None:
    """A thermostat without LocalTemperature still has the sensor, with an unknown value."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=0)
    del shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:LocalTemperature_x100"]
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator, "local_temperature")

    assert entity.native_value is None
    assert entity.available is True


async def test_set_temperature_shows_on_the_setpoint_sensor() -> None:
    """The setpoint sensor follows the optimistic target, and the room temperature does not."""

    coordinator, _, _ = await create_coordinator()

    with patch(CALL_LATER):
        await coordinator.async_set_temperature(fixtures.THERMOSTAT_ID, 21.5)

    assert _entity(coordinator, "heating_setpoint").native_value == 21.5
    assert _entity(coordinator, "local_temperature").native_value == 22.0


async def test_climate_device_skips_the_legacy_temperature_sensor() -> None:
    """A thermostat that also has a temperature field does not grow a second scaled sensor."""

    coordinator, _, _ = await create_coordinator()
    coordinator.data[fixtures.THERMOSTAT_ID]["temperature"] = 2200
    coordinator.data["hall"] = {
        "id": "hall",
        "type": "temperature_sensor",
        "name": "Hall",
        "_gateway_id": fixtures.GATEWAY_ID,
        "temperature": 19.5,
        "_fresh": True,
    }
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()

    await sensor.async_setup_entry(MagicMock(), entry, add_entities)

    entities = {entity.unique_id: entity for entity in add_entities.call_args.args[0]}
    assert _uid(fixtures.THERMOSTAT_ID, "temperature") not in entities
    assert _uid(fixtures.THERMOSTAT_ID, "local_temperature") in entities
    hall = entities[_uid("hall", "temperature")]
    assert hall.native_value == 19.5
    assert hall.unique_id == _uid("hall", "temperature")
    assert hall.translation_key == "temperature"
    assert hall.has_entity_name is False


async def test_humidity_and_battery_keys_create_no_sensors() -> None:
    """REST humidity and battery keys do not become sensors."""

    coordinator, _, _ = await create_coordinator()
    coordinator.data["spare"] = {
        "id": "spare",
        "type": "sensor",
        "name": "Spare",
        "_gateway_id": fixtures.GATEWAY_ID,
        "humidity": 40,
        "battery": 90,
        "battery_level": 90,
        "status": {"humidity": 40, "battery": 90},
        "_fresh": True,
    }
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()

    await sensor.async_setup_entry(MagicMock(), entry, add_entities)

    assert [entity.unique_id for entity in add_entities.call_args.args[0]] == [
        _uid(fixtures.THERMOSTAT_ID, "local_temperature"),
        _uid(fixtures.THERMOSTAT_ID, "heating_setpoint"),
        _uid(fixtures.THERMOSTAT_2_ID, "local_temperature"),
        _uid(fixtures.THERMOSTAT_2_ID, "heating_setpoint"),
    ]


LEVEL = "ep9:sIT600TH:BatteryLevel"
RSSI = "ep9:sIT600I:LastMessageRSSI_d"
LQI = "ep9:sIT600I:LastMessageLQI_d"
LATER_ID = "20000000-0000-4000-8000-000000000099"


async def _coordinator_with(**properties: object):
    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=0)
    shadow["state"]["reported"]["11"]["properties"].update(properties)
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    return await create_coordinator(api)


def _setup_sensors(coordinator: object) -> tuple[MagicMock, MagicMock]:
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    return entry, add_entities


def _added(add_entities: MagicMock) -> dict[str, object]:
    entities: dict[str, object] = {}
    if not add_entities.called:
        return entities
    for call in add_entities.call_args_list:
        for entity in call.args[0]:
            entities[entity.unique_id] = entity
    return entities


async def _sensor_entities(coordinator: object) -> dict[str, object]:
    entry, add_entities = _setup_sensors(coordinator)
    await sensor.async_setup_entry(MagicMock(), entry, add_entities)
    return _added(add_entities)


async def test_battery_level_zero_is_a_raw_diagnostic() -> None:
    """A present 0 is the reading. It is not unknown, not a percentage, and not volts."""

    coordinator, _, _ = await _coordinator_with(**{LEVEL: 0, "ep9:sBasicS:BatteryVoltage": 30})
    entities = await _sensor_entities(coordinator)
    entity = entities[_uid(fixtures.THERMOSTAT_ID, "battery_level")]

    assert isinstance(entity, SalusDiagnosticSensor)
    assert entity.native_value == 0
    assert entity.device_class is None
    assert entity.native_unit_of_measurement is None
    assert entity.entity_category is EntityCategory.DIAGNOSTIC
    assert entity.state_class is SensorStateClass.MEASUREMENT
    assert entity.name == "Apartmán A Termostat pokoj Battery level"
    assert entity.translation_key == "battery_level"
    assert entity.has_entity_name is False
    assert _uid(fixtures.THERMOSTAT_2_ID, "battery_level") not in entities


async def test_battery_level_five_stays_five() -> None:
    """The observed raw level 5 is not scaled into a percent."""

    coordinator, _, _ = await _coordinator_with(**{LEVEL: 5})
    entities = await _sensor_entities(coordinator)

    assert entities[_uid(fixtures.THERMOSTAT_ID, "battery_level")].native_value == 5


async def test_missing_battery_level_is_unknown_on_an_existing_sensor() -> None:
    """The sensor stays after the key leaves. The value is unknown, and the entity stays available."""

    coordinator, _, _ = await _coordinator_with(**{LEVEL: 5})
    entity = (await _sensor_entities(coordinator))[_uid(fixtures.THERMOSTAT_ID, "battery_level")]
    entity.hass = MagicMock()
    del coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"][LEVEL]

    assert entity.native_value is None
    assert entity.available is True


async def test_signal_strength_and_link_quality_follow_their_own_keys() -> None:
    """RSSI is signal strength in dBm. LQI is a unitless diagnostic. Another endpoint does not count."""

    coordinator, _, _ = await _coordinator_with(**{RSSI: -62, LQI: 180, "ep7:sIT600I:LastMessageRSSI_d": -10})
    entities = await _sensor_entities(coordinator)
    rssi = entities[_uid(fixtures.THERMOSTAT_ID, "signal_strength")]
    lqi = entities[_uid(fixtures.THERMOSTAT_ID, "link_quality")]

    assert rssi.native_value == -62
    assert rssi.device_class is SensorDeviceClass.SIGNAL_STRENGTH
    assert rssi.native_unit_of_measurement == SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    assert rssi.entity_category is EntityCategory.DIAGNOSTIC
    assert rssi.name == "Apartmán A Termostat pokoj Signal strength"
    assert rssi.translation_key == "signal_strength"
    assert rssi.has_entity_name is False
    assert lqi.native_value == 180
    assert lqi.device_class is None
    assert lqi.native_unit_of_measurement is None
    assert lqi.entity_category is EntityCategory.DIAGNOSTIC
    assert lqi.state_class is SensorStateClass.MEASUREMENT
    assert lqi.name == "Apartmán A Termostat pokoj Link quality"
    assert lqi.translation_key == "link_quality"
    assert lqi.has_entity_name is False


async def test_rssi_without_lqi_creates_only_the_signal_sensor() -> None:
    coordinator, _, _ = await _coordinator_with(**{RSSI: -40})
    unique_ids = list(await _sensor_entities(coordinator))

    assert _uid(fixtures.THERMOSTAT_ID, "signal_strength") in unique_ids
    assert _uid(fixtures.THERMOSTAT_ID, "link_quality") not in unique_ids


async def test_later_thermostat_with_battery_level_zero_gets_the_sensor() -> None:
    """A thermostat that shows up later is discovered with the cells it already reports."""

    coordinator, _, _ = await create_coordinator()
    entry, add_entities = _setup_sensors(coordinator)
    await sensor.async_setup_entry(MagicMock(), entry, add_entities)

    updated = dict(coordinator.data)
    updated[LATER_ID] = {
        "id": LATER_ID,
        "name": "Termostat novy",
        "model": "SQ610RF",
        "_gateway_id": fixtures.GATEWAY_ID,
        "_shadow_properties": {LEVEL: 0},
        "_fresh": True,
    }
    coordinator.async_set_updated_data(updated)

    added = {entity.unique_id: entity for entity in add_entities.call_args.args[0]}
    battery = added[_uid(LATER_ID, "battery_level")]
    assert battery.native_value == 0
    assert _uid(LATER_ID, "signal_strength") not in added


async def test_battery_level_that_appears_later_is_added_once() -> None:
    """A cell that shows up after the first snapshot still gets a sensor. A repeat does not add another."""

    coordinator, _, _ = await create_coordinator()
    entry, add_entities = _setup_sensors(coordinator)
    await sensor.async_setup_entry(MagicMock(), entry, add_entities)
    assert _uid(fixtures.THERMOSTAT_ID, "battery_level") not in _added(add_entities)

    properties = dict(coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"])
    properties[LEVEL] = 0
    coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"] = properties
    coordinator.async_set_updated_data(dict(coordinator.data))
    entity = _added(add_entities)[_uid(fixtures.THERMOSTAT_ID, "battery_level")]
    assert entity.native_value == 0

    calls = add_entities.call_count
    coordinator.async_set_updated_data({})
    coordinator.async_set_updated_data(dict(coordinator.data))
    assert add_entities.call_count == calls


COOLING = "ep9:sIT600TH:CoolingSetpoint_x100"
COOLING_CONTROL = "ep9:sIT600TH:CoolingControl"


async def test_cooling_setpoint_is_a_measurement_when_the_key_is_present() -> None:
    """The sensor shows degrees. It is not a diagnostic, and the other thermostat does not get one."""

    coordinator, _, _ = await _coordinator_with(**{COOLING: 1800, COOLING_CONTROL: 0})
    entities = await _sensor_entities(coordinator)
    entity = entities[_uid(fixtures.THERMOSTAT_ID, "cooling_setpoint")]

    assert isinstance(entity, SalusHeatingTemperature)
    assert entity.native_value == 18.0
    assert entity.state_class is SensorStateClass.MEASUREMENT
    assert entity.device_class is SensorDeviceClass.TEMPERATURE
    assert entity.native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert entity.suggested_display_precision == 1
    assert entity.entity_category is None
    assert entity.translation_key == "cooling_setpoint"
    assert entity.name == "Apartmán A Termostat pokoj Cooling setpoint"
    assert entity.has_entity_name is False
    assert _uid(fixtures.THERMOSTAT_2_ID, "cooling_setpoint") not in entities


async def test_cooling_control_without_a_setpoint_still_adds_the_sensor() -> None:
    coordinator, _, _ = await _coordinator_with(**{COOLING_CONTROL: 1})
    entity = (await _sensor_entities(coordinator))[_uid(fixtures.THERMOSTAT_ID, "cooling_setpoint")]

    assert entity.native_value is None


async def test_disabled_cooling_without_a_setpoint_adds_no_sensor() -> None:
    coordinator, _, _ = await _coordinator_with(**{COOLING_CONTROL: 0})

    assert _uid(fixtures.THERMOSTAT_ID, "cooling_setpoint") not in await _sensor_entities(coordinator)


async def test_bool_cooling_control_is_not_enabled() -> None:
    coordinator, _, _ = await _coordinator_with(**{COOLING_CONTROL: True})

    assert _uid(fixtures.THERMOSTAT_ID, "cooling_setpoint") not in await _sensor_entities(coordinator)


async def test_present_non_int_cooling_setpoint_is_unknown() -> None:
    coordinator, _, _ = await _coordinator_with(**{COOLING: True})
    entity = (await _sensor_entities(coordinator))[_uid(fixtures.THERMOSTAT_ID, "cooling_setpoint")]

    assert entity.native_value is None


async def test_zero_cooling_setpoint_is_zero_degrees() -> None:
    coordinator, _, _ = await _coordinator_with(**{COOLING: 0})
    entity = (await _sensor_entities(coordinator))[_uid(fixtures.THERMOSTAT_ID, "cooling_setpoint")]

    assert entity.native_value == 0.0


async def test_cooling_setpoint_that_appears_later_is_added_once() -> None:
    """A setpoint key that shows up after setup still gets one sensor. A repeat does not add another."""

    coordinator, _, _ = await create_coordinator()
    entry, add_entities = _setup_sensors(coordinator)
    await sensor.async_setup_entry(MagicMock(), entry, add_entities)
    assert _uid(fixtures.THERMOSTAT_ID, "cooling_setpoint") not in _added(add_entities)

    properties = dict(coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"])
    properties[COOLING] = 1900
    coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"] = properties
    coordinator.async_set_updated_data(dict(coordinator.data))
    entity = _added(add_entities)[_uid(fixtures.THERMOSTAT_ID, "cooling_setpoint")]
    assert entity.native_value == 19.0

    calls = add_entities.call_count
    coordinator.async_set_updated_data({})
    coordinator.async_set_updated_data(dict(coordinator.data))
    assert add_entities.call_count == calls
