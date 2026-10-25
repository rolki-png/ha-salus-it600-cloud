"""Thermostat observation parsed from shadow properties and from raw cells."""

import pytest

from custom_components.salus_it600_cloud.heating import (
    CentiCelsius,
    Demand,
    HeatingAction,
    IntCell,
    ThermostatCommand,
    ThermostatObservation,
    centi_celsius_from_degrees,
    decode_running_cell,
    decode_x100_cell,
    desired_to_reported_thermostat,
    diagnostics,
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
LEVEL = "ep9:sIT600TH:BatteryLevel"
RSSI = "ep9:sIT600I:LastMessageRSSI_d"
LQI = "ep9:sIT600I:LastMessageLQI_d"
LOCK = "ep9:sIT600TH:LockKey"
ERROR_01 = "ep9:sIT600TH:Error01"
ERROR_06 = "ep9:sIT600TH:Error06"
ERROR_32 = "ep9:sIT600TH:Error32"
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


def test_empty_map_has_no_diagnostics() -> None:
    assert diagnostics({}) is None


def test_battery_level_zero_is_a_raw_reading() -> None:
    """BatteryLevel 0 and 5 are raw levels. Voltage tenths and a bool are not that level."""

    zero = diagnostics(_properties(**{LEVEL: 0}))
    five = diagnostics(_properties(**{LEVEL: 5}))
    voltage_only = diagnostics(_properties())
    garbage = diagnostics(_properties(**{LEVEL: True}))

    assert zero is not None and zero.battery_level.value == 0
    assert zero.battery_level.present is True
    assert five is not None and five.battery_level.value == 5
    assert voltage_only is not None and voltage_only.battery_level.present is False
    assert voltage_only.battery_level.value is None
    assert observe(_properties()).battery is not None
    assert observe(_properties()).battery.volts() == 3.0
    assert garbage is not None and garbage.battery_level.present is True
    assert garbage.battery_level.value is None


def test_radio_cells_are_the_thermostat_endpoint() -> None:
    """ep9 signal cells are the readings. The same name on another endpoint is not."""

    other = "ep7:sIT600I:LastMessageRSSI_d"
    reading = diagnostics(_properties(**{RSSI: -62, LQI: 180, other: -10}))
    only_other = diagnostics(_properties(**{other: -10, "ep8:sIT600I:LastMessageLQI_d": 20}))

    assert reading is not None
    assert reading.rssi_dbm.value == -62
    assert reading.lqi.value == 180
    assert only_other is not None
    assert only_other.rssi_dbm.present is False
    assert only_other.lqi.present is False


def test_error_codes_are_the_integer_ones() -> None:
    """Any Error01..Error32 integer 1 is active. A bool, a zero, and other clusters are not."""

    quiet = diagnostics(_properties(**{ERROR_01: 0, ERROR_06: 0}))
    active = diagnostics(
        _properties(
            **{
                ERROR_32: 1,
                ERROR_01: 0,
                ERROR_06: 1,
                "ep9:sIT600TH:Error09": True,
                "ep9:sIT600TH:Error33": 1,
                "ep9:sIT600TH:Error00": 1,
                "ep8:sIT600WC:Error10": 1,
            }
        )
    )
    missing = diagnostics(_properties())
    boolean = diagnostics(_properties(**{ERROR_01: True}))

    assert quiet is not None and quiet.errors.known is True
    assert quiet.errors.is_on() is False
    assert quiet.errors.active == ()
    assert active is not None and active.errors.is_on() is True
    assert active.errors.active == ("Error06", "Error32")
    assert missing is not None and missing.errors.known is False
    assert missing.errors.is_on() is None
    assert missing.errors.active == ()
    assert boolean is not None and boolean.errors.known is True
    assert boolean.errors.is_on() is False
    assert boolean.errors.active == ()


def test_lock_key_is_locked_only_for_integer_one() -> None:
    locked = diagnostics(_properties(**{LOCK: 1}))
    unlocked = diagnostics(_properties(**{LOCK: 0}))
    absent = diagnostics(_properties())
    boolean = diagnostics(_properties(**{LOCK: True}))
    other = diagnostics(_properties(**{LOCK: 5}))

    assert locked is not None and locked.lock.is_locked() is True
    assert unlocked is not None and unlocked.lock.cell.present is True
    assert unlocked.lock.is_locked() is False
    assert absent is not None and absent.lock.cell.present is False
    assert absent.lock.is_locked() is None
    assert boolean is not None and boolean.lock.cell.present is True
    assert boolean.lock.is_locked() is None
    assert other is not None and other.lock.is_locked() is None


def test_lock_command_name_is_the_name_diagnostics_reads() -> None:
    """Pending overlay and the parser share one write-name to read-name pair."""

    reported_name = desired_to_reported_thermostat()[ThermostatCommand.LOCK]
    reading = diagnostics({reported_name: 1})

    assert ThermostatCommand.LOCK == "ep9:sIT600TH:SetLockKey"
    assert reported_name == LOCK
    assert reading is not None and reading.lock.is_locked() is True
    assert ThermostatCommand.LOCK not in desired_to_reported_thermostat().values()


def test_bool_cannot_pose_as_a_raw_level() -> None:
    with pytest.raises(ValueError):
        IntCell(present=True, value=True)
