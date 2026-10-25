"""Tests for Salus thermostat entities."""

from collections.abc import Awaitable, Callable
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACAction, HVACMode

from custom_components.salus_it600_cloud import climate
from custom_components.salus_it600_cloud.climate import SalusCloudClimate

from . import fixtures
from .helpers import CALL_LATER, FakeApi, create_coordinator


def _entity(coordinator: object, device_id: str = fixtures.THERMOSTAT_ID) -> SalusCloudClimate:
    entity = SalusCloudClimate(coordinator, device_id, coordinator.data[device_id])
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


async def test_setup_creates_thermostats_only() -> None:
    """Climate entities are created for thermostats, not for relays or the gateway."""

    coordinator, _, _ = await create_coordinator()
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()

    await climate.async_setup_entry(MagicMock(), entry, add_entities)

    assert [entity.unique_id for entity in add_entities.call_args.args[0]] == [
        f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{fixtures.THERMOSTAT_ID}",
        f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{fixtures.THERMOSTAT_2_ID}",
    ]


async def test_entity_name_is_unchanged() -> None:
    """Existing names (and therefore entity ids) of thermostats stay the same."""

    coordinator, _, _ = await create_coordinator()
    entity = _entity(coordinator)

    assert entity.name == "Apartmán A Termostat pokoj"
    assert entity.unique_id == f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{fixtures.THERMOSTAT_ID}"
    assert entity.has_entity_name is False
    assert entity.translation_key == "thermostat"


async def test_schedule_mode_state() -> None:
    """Thermostat following its schedule is heating with schedule preset."""

    api = FakeApi()
    api.shadows[fixtures.THERMOSTAT_CODE] = fixtures.thermostat_shadow(
        hold_type=0, temperature_x100=2250, setpoint_x100=2100
    )
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert (entity.hvac_mode, entity.preset_mode, entity.hvac_action) == (HVACMode.HEAT, "schedule", HVACAction.IDLE)
    assert (entity.current_temperature, entity.target_temperature) == (22.5, 21.0)


async def test_manual_mode_actively_heating() -> None:
    """Running state reports active heating."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=2)
    shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:RunningState"] = 1
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert (entity.hvac_mode, entity.preset_mode, entity.hvac_action) == (HVACMode.HEAT, "manual", HVACAction.HEATING)


async def test_standby_mode_state() -> None:
    """Thermostat in stand-by (frost protection) is off when demand was reported."""

    api = FakeApi()
    api.shadows[fixtures.THERMOSTAT_CODE] = fixtures.thermostat_shadow(hold_type=7)
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert (entity.hvac_mode, entity.preset_mode, entity.hvac_action) == (HVACMode.OFF, "away", HVACAction.OFF)


async def test_missing_running_state_stays_unknown_in_heat() -> None:
    """Heat mode with no RunningState is unknown, not idle."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=0)
    del shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:RunningState"]
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert entity.hvac_mode is HVACMode.HEAT
    assert entity.hvac_action is None
    assert "running_state" not in entity.extra_state_attributes


async def test_standby_without_running_state_is_not_off_action() -> None:
    """Stand-by does not hide a missing RunningState behind HVACAction.OFF."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=7)
    del shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:RunningState"]
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert entity.hvac_mode is HVACMode.OFF
    assert entity.preset_mode == "away"
    assert entity.hvac_action is None


@pytest.mark.parametrize("running", [True, False, None, 1.0])
async def test_unreadable_running_state_is_unknown_action(running: object) -> None:
    """A present non-integer RunningState is unknown, including bool True which equals 1."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=2)
    shadow["state"]["reported"]["11"]["properties"]["ep9:sIT600TH:RunningState"] = running
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)
    entity = _entity(coordinator)

    assert entity.hvac_mode is HVACMode.HEAT
    assert entity.hvac_action is None
    assert "running_state" not in entity.extra_state_attributes


async def test_attributes_follow_the_observation() -> None:
    """Cards keep the same attribute names, filled from the observation."""

    coordinator, _, _ = await create_coordinator()

    assert _entity(coordinator).extra_state_attributes == {
        "hold_type": "Schedule",
        "system_mode": "Heat",
        "battery_voltage": "3.0V",
        "running_state": "Idle",
    }


async def test_thermostat_without_reported_state_is_unavailable() -> None:
    """A thermostat without state data is unavailable instead of showing made-up heat/manual values."""

    api = FakeApi()
    del api.shadows[fixtures.THERMOSTAT_CODE]
    coordinator, _, _ = await create_coordinator(api)

    assert _entity(coordinator).available is False
    assert _entity(coordinator, fixtures.THERMOSTAT_2_ID).available is True


@pytest.mark.parametrize(
    ("action", "hold_type"),
    [
        (lambda entity: entity.async_set_hvac_mode(HVACMode.OFF), 7),
        (lambda entity: entity.async_set_hvac_mode(HVACMode.HEAT), 0),
        (lambda entity: entity.async_set_preset_mode("schedule"), 0),
        (lambda entity: entity.async_set_preset_mode("manual"), 2),
        (lambda entity: entity.async_set_preset_mode("away"), 7),
        (lambda entity: entity.async_turn_off(), 7),
        (lambda entity: entity.async_turn_on(), 0),
    ],
    ids=["hvac-off", "hvac-heat", "preset-schedule", "preset-manual", "preset-away", "turn-off", "turn-on"],
)
async def test_mode_commands_set_hold_type(
    action: Callable[[SalusCloudClimate], Awaitable[None]], hold_type: int
) -> None:
    """Mode changes are sent as hold type of the thermostat."""

    coordinator, connection, _ = await create_coordinator()
    entity = _entity(coordinator)

    with patch(CALL_LATER):
        await action(entity)

    assert connection.published == [(fixtures.THERMOSTAT_CODE, "11", {"ep9:sIT600TH:SetHoldType": hold_type})]


async def test_turning_off_one_thermostat_turns_off_all_with_sync() -> None:
    """With synchronization, turning off one thermostat turns off every thermostat of the apartment at once."""

    coordinator, connection, _ = await create_coordinator(sync=True)
    entity = _entity(coordinator)

    with patch(CALL_LATER):
        await entity.async_turn_off()

    assert sorted(code for code, _, _ in connection.published) == sorted(
        [fixtures.THERMOSTAT_CODE, fixtures.THERMOSTAT_2_CODE]
    )
    assert _entity(coordinator, fixtures.THERMOSTAT_2_ID).hvac_mode == HVACMode.OFF
    assert entity.supported_features & ClimateEntityFeature.TURN_OFF


async def test_set_temperature_shows_new_target_immediately() -> None:
    """New target temperature is shown right after the command, before the device reports it."""

    coordinator, connection, _ = await create_coordinator()
    entity = _entity(coordinator)

    with patch(CALL_LATER):
        await entity.async_set_temperature(temperature=21.5)

    assert connection.published == [
        (
            fixtures.THERMOSTAT_CODE,
            "11",
            {
                "ep9:sIT600TH:SetHeatingSetpoint_x100": 2150,
                "ep9:sIT600TH:SetHoldType": 2,
                "ep9:sIT600TH:SetSystemMode": 4,
            },
        )
    ]
    assert entity.target_temperature == 21.5
    assert entity.preset_mode == "manual"


MIN_HEAT = "ep9:sIT600TH:MinHeatSetpoint_x100"
MAX_HEAT = "ep9:sIT600TH:MaxHeatSetpoint_x100"


async def _climate_with(**properties: object) -> SalusCloudClimate:
    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=0)
    shadow["state"]["reported"]["11"]["properties"].update(properties)
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, _, _ = await create_coordinator(api)
    return _entity(coordinator)


@pytest.mark.parametrize(
    ("minimum", "maximum", "low", "high"),
    [
        (500, 3500, 5.0, 35.0),
        (700, 3200, 7.0, 32.0),
        (0, 4000, 0.0, 40.0),
    ],
)
async def test_min_and_max_temp_follow_reported_heat_limits(
    minimum: int, maximum: int, low: float, high: float
) -> None:
    """The slider range is the reported heat limits. Mode stays heat, and presets stay schedule, manual, and away."""

    entity = await _climate_with(**{MIN_HEAT: minimum, MAX_HEAT: maximum})

    assert entity.min_temp == low
    assert entity.max_temp == high
    assert entity.hvac_mode is HVACMode.HEAT
    assert entity.hvac_modes == [HVACMode.HEAT, HVACMode.OFF]
    assert entity.preset_mode == "schedule"
    assert entity.preset_modes == ["schedule", "manual", "away"]


async def test_missing_heat_limits_keep_five_and_thirty_five() -> None:
    """No limit cells, and an empty shadow, both keep 5°C and 35°C."""

    coordinator, _, _ = await create_coordinator()
    entity = _entity(coordinator)

    assert (entity.min_temp, entity.max_temp) == (5.0, 35.0)

    coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"] = {}
    assert (entity.min_temp, entity.max_temp) == (5.0, 35.0)


async def test_one_heat_limit_leaves_the_other_default() -> None:
    entity = await _climate_with(**{MIN_HEAT: 700})

    assert entity.min_temp == 7.0
    assert entity.max_temp == 35.0


async def test_unreadable_heat_limit_keeps_the_default() -> None:
    entity = await _climate_with(**{MIN_HEAT: True, MAX_HEAT: 32.0})

    assert entity.min_temp == 5.0
    assert entity.max_temp == 35.0


async def test_cooling_cells_do_not_add_a_cool_mode() -> None:
    """A reported cooling setpoint does not change heat, off, or the three presets."""

    entity = await _climate_with(
        **{
            "ep9:sIT600TH:CoolingControl": 1,
            "ep9:sIT600TH:CoolingSetpoint_x100": 1800,
        }
    )

    assert entity.hvac_mode is HVACMode.HEAT
    assert entity.hvac_modes == [HVACMode.HEAT, HVACMode.OFF]
    assert entity.preset_modes == ["schedule", "manual", "away"]
    assert (entity.min_temp, entity.max_temp) == (5.0, 35.0)
    assert entity.target_temperature == 21.0
