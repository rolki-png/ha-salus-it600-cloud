"""Thermostat observation parsed from shadow properties and from raw cells."""

import pytest

from custom_components.salus_it600_cloud.heating import (
    CentiCelsius,
    Demand,
    HeatingAction,
    ThermostatCommand,
    ThermostatObservation,
    centi_celsius_from_degrees,
    decode_running_cell,
    decode_x100_cell,
    desired_to_reported_thermostat,
    heating_action,
    hold_raw_for_preset,
    observation_from_cells,
    observe,
)

RUNNING = "ep9:sIT600TH:RunningState"
LOCAL = "ep9:sIT600TH:LocalTemperature_x100"
SETPOINT = "ep9:sIT600TH:HeatingSetpoint_x100"
HOLD = "ep9:sIT600TH:HoldType"
SYSTEM = "ep9:sIT600TH:SystemMode"
BATTERY = "ep9:sBasicS:BatteryVoltage"
_DELETE = object()


def _properties(**overrides: object) -> dict[str, object]:
    properties: dict[str, object] = {
        HOLD: 2,
        SYSTEM: 4,
        RUNNING: 0,
        LOCAL: 2200,
        SETPOINT: 2100,
        BATTERY: 30,
    }
    for key, value in overrides.items():
        if value is _DELETE:
            del properties[key]
        else:
            properties[key] = value
    return properties


def test_empty_property_map_is_not_an_observation() -> None:
    """An empty shadow is the same as no reported state, not a zeroed thermostat."""

    assert observe({}) is None


def test_non_empty_map_with_no_thermostat_keys_is_unreported() -> None:
    """A relay-only property still produces an observation whose demand was not reported."""

    observation = observe({"ep9:sOnOffS:OnOff": 1})

    assert observation is not None
    assert observation.demand is Demand.UNREPORTED
    assert observation.demand.is_on() is None
    assert observation.local_temperature is None
    assert observation.heating_setpoint is None
    assert observation.preset_slug() is None
    assert heating_action(observation) is HeatingAction.UNKNOWN


@pytest.mark.parametrize(
    ("present", "value", "demand"),
    [
        (False, None, Demand.UNREPORTED),
        (True, None, Demand.UNREADABLE),
        (True, True, Demand.UNREADABLE),
        (True, False, Demand.UNREADABLE),
        (True, 1.0, Demand.UNREADABLE),
        (True, "1", Demand.UNREADABLE),
        (True, 0, Demand.IDLE),
        (True, 2, Demand.IDLE),
        (True, 1, Demand.HEATING),
    ],
)
def test_running_cell_keeps_missing_idle_and_garbage_apart(present: bool, value: object, demand: Demand) -> None:
    """RunningState 0 is idle, 1 is heating, and a bool is not heating just because True == 1."""

    assert decode_running_cell(value, present=present) is demand


def test_observe_uses_the_running_cell_decoder() -> None:
    """A present bool on the shadow is unreadable, not idle and not heating."""

    assert observe(_properties(**{RUNNING: True})).demand is Demand.UNREADABLE
    assert observe(_properties(**{RUNNING: _DELETE})).demand is Demand.UNREPORTED
    assert observe(_properties(**{RUNNING: 0})).demand is Demand.IDLE
    assert observe(_properties(**{RUNNING: 1})).demand is Demand.HEATING


@pytest.mark.parametrize(
    ("demand", "is_on"),
    [
        (Demand.UNREPORTED, None),
        (Demand.UNREADABLE, None),
        (Demand.IDLE, False),
        (Demand.HEATING, True),
    ],
)
def test_demand_is_on_is_unknown_unless_the_cell_was_an_int(demand: Demand, is_on: bool | None) -> None:
    assert demand.is_on() is is_on


def test_unreported_and_unreadable_demand_stay_unknown_in_standby() -> None:
    """Standby does not turn a missing or garbage RunningState into off or idle."""

    missing = observe(_properties(**{HOLD: 7, RUNNING: _DELETE}))
    garbage = observe(_properties(**{HOLD: 7, SYSTEM: 0, RUNNING: True}))
    null_cell = observe(_properties(**{RUNNING: None}))

    assert heating_action(missing) is HeatingAction.UNKNOWN
    assert heating_action(garbage) is HeatingAction.UNKNOWN
    assert heating_action(null_cell) is HeatingAction.UNKNOWN
    assert missing.demand.is_on() is None
    assert garbage.demand.attribute_label() is None


def test_known_demand_in_standby_or_system_off_is_off_even_while_calling() -> None:
    """Frost protection and system mode 0 report off once demand itself was an int."""

    standby_idle = observe(_properties(**{HOLD: 7, RUNNING: 0}))
    standby_calling = observe(_properties(**{HOLD: 7, RUNNING: 1}))
    system_off_calling = observe(_properties(**{HOLD: 2, SYSTEM: 0, RUNNING: 1}))

    assert heating_action(standby_idle) is HeatingAction.OFF
    assert heating_action(standby_calling) is HeatingAction.OFF
    assert heating_action(system_off_calling) is HeatingAction.OFF
    assert standby_calling.demand.is_on() is True
    assert standby_idle.demand.attribute_label() == "Idle"
    assert standby_calling.demand.attribute_label() == "Heating"


def test_heat_mode_action_follows_integer_demand() -> None:
    assert heating_action(observe(_properties(**{RUNNING: 1}))) is HeatingAction.HEATING
    assert heating_action(observe(_properties(**{RUNNING: 0}))) is HeatingAction.IDLE
    assert heating_action(observe(_properties(**{RUNNING: 2}))) is HeatingAction.IDLE
    assert heating_action(None) is HeatingAction.UNKNOWN


def test_zero_temperature_is_a_real_sample_and_garbage_is_not() -> None:
    """0 hundredths is 0.0°C. A missing key and a bool are both no sample."""

    assert decode_x100_cell(0, present=True).celsius() == 0.0
    assert decode_x100_cell(2250, present=True).celsius() == 22.5
    assert decode_x100_cell(0, present=False) is None
    assert decode_x100_cell(None, present=True) is None
    assert decode_x100_cell(True, present=True) is None
    assert decode_x100_cell(22.5, present=True) is None

    zero = observe(_properties(**{LOCAL: 0, SETPOINT: _DELETE}))
    assert zero.local_temperature.celsius() == 0.0
    assert zero.heating_setpoint is None
    assert observe(_properties(**{LOCAL: True})).local_temperature is None


def test_scale_pair_round_trips_setpoints() -> None:
    """The command scale and the read scale are the same factor."""

    for degrees in (0.0, 5.0, 21.5, 22.5, 35.0):
        assert CentiCelsius(centi_celsius_from_degrees(degrees)).celsius() == degrees


def test_setpoint_command_name_is_the_name_observe_reads() -> None:
    """Pending overlay and the parser share one write-name to read-name pair."""

    reported_name = desired_to_reported_thermostat()[ThermostatCommand.SETPOINT]
    observation = observe({reported_name: centi_celsius_from_degrees(21.5)})

    assert observation.heating_setpoint.celsius() == 21.5
    assert ThermostatCommand.SETPOINT not in desired_to_reported_thermostat().values()


def test_hold_and_system_commands_match_preset_and_mode() -> None:
    mapping = desired_to_reported_thermostat()
    observation = observe(
        {
            mapping[ThermostatCommand.HOLD]: hold_raw_for_preset("away"),
            mapping[ThermostatCommand.SYSTEM_MODE]: 0,
        }
    )

    assert observation.preset_slug() == "away"
    assert observation.hold.is_standby is True
    assert observation.hold_label() == "Frost Protection"
    assert observation.system_mode.is_off is True
    assert observation.system_mode_label() == "Off"


@pytest.mark.parametrize(
    ("raw", "slug", "label", "standby"),
    [
        (0, "schedule", "Schedule", False),
        (2, "manual", "Manual Hold", False),
        (7, "away", "Frost Protection", True),
        (3, "manual", "Unknown (3)", False),
    ],
)
def test_hold_presets(raw: int, slug: str, label: str, standby: bool) -> None:
    observation = observe(_properties(**{HOLD: raw}))

    assert observation.preset_slug() == slug
    assert observation.hold_label() == label
    assert observation.hold.is_standby is standby


def test_preset_slugs_are_the_hold_command_values() -> None:
    assert [hold_raw_for_preset(slug) for slug in ("schedule", "manual", "away")] == [0, 2, 7]


def test_absent_hold_has_no_preset_and_present_non_int_is_manual() -> None:
    absent = observe(_properties(**{HOLD: _DELETE}))
    garbage = observe(_properties(**{HOLD: True}))

    assert absent.preset_slug() is None
    assert absent.hold_label() is None
    assert absent.hold.is_standby is False
    assert garbage.preset_slug() == "manual"
    assert garbage.hold_label() == "Unknown"
    assert garbage.hold.is_standby is False


def test_system_mode_labels() -> None:
    assert observe(_properties(**{SYSTEM: 4})).system_mode_label() == "Heat"
    assert observe(_properties(**{SYSTEM: 1})).system_mode_label() == "Auto"
    assert observe(_properties(**{SYSTEM: 9})).system_mode_label() == "Unknown (9)"
    assert observe(_properties(**{SYSTEM: _DELETE})).system_mode_label() is None
    assert observe(_properties(**{SYSTEM: False})).system_mode.is_off is False


def test_battery_tenths_become_volts() -> None:
    assert observe(_properties()).battery.volts() == 3.0
    assert observe(_properties(**{BATTERY: _DELETE})).battery is None
    assert observe(_properties(**{BATTERY: True})).battery is None


def test_history_cells_do_not_need_wire_keys() -> None:
    """Cube rows pass cells straight in. They do not rebuild an ep9 property map."""

    observation = observation_from_cells(
        running=1,
        running_present=True,
        local_x100=0,
        local_present=True,
        setpoint_x100=None,
        setpoint_present=False,
        hold=2,
        hold_present=True,
        system_mode=4,
        system_mode_present=True,
        battery_tenths=30,
        battery_present=True,
    )

    assert observation.demand is Demand.HEATING
    assert observation.local_temperature.celsius() == 0.0
    assert observation.heating_setpoint is None
    assert observation.preset_slug() == "manual"
    assert observation.battery.volts() == 3.0


def test_bool_cannot_pose_as_hundredths() -> None:
    with pytest.raises(TypeError):
        CentiCelsius(True)


def test_observation_rejects_a_raw_float_temperature() -> None:
    with pytest.raises(TypeError):
        ThermostatObservation(
            demand=Demand.IDLE,
            local_temperature=22.5,
            heating_setpoint=None,
            hold=observe(_properties()).hold,
            system_mode=observe(_properties()).system_mode,
            battery=None,
        )


def test_unknown_preset_slug_is_rejected() -> None:
    with pytest.raises(KeyError):
        hold_raw_for_preset("boost")
