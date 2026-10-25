"""Thermostat observation parsed from merged shadow properties.

Wire names stay in this module. Platforms call observe(), diagnostics(), and the catalogs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Demand(Enum):
    """Call for heat as reported by one RunningState cell."""

    UNREPORTED = "unreported"
    UNREADABLE = "unreadable"
    IDLE = "idle"
    HEATING = "heating"

    def is_on(self) -> bool | None:
        """Binary-sensor state. None is unknown, not off."""
        if self is Demand.HEATING:
            return True
        if self is Demand.IDLE:
            return False
        if self is Demand.UNREPORTED or self is Demand.UNREADABLE:
            return None
        raise RuntimeError(self)

    def attribute_label(self) -> str | None:
        """Climate attribute. Omitted when the cell was not an integer demand."""
        if self is Demand.HEATING:
            return "Heating"
        if self is Demand.IDLE:
            return "Idle"
        if self is Demand.UNREPORTED or self is Demand.UNREADABLE:
            return None
        raise RuntimeError(self)


class HeatingAction(Enum):
    """Climate hvac_action before the Home Assistant enum mapping.

    UNKNOWN wins whenever demand is unreported or unreadable, including standby
    and system-mode off. OFF is standby or system mode 0 with a reported demand.
    """

    UNKNOWN = "unknown"
    OFF = "off"
    IDLE = "idle"
    HEATING = "heating"


@dataclass(frozen=True)
class CentiCelsius:
    """Hundredths of a degree Celsius. The shadow's x100 unit."""

    hundredths: int

    def __post_init__(self) -> None:
        if type(self.hundredths) is not int:
            raise TypeError("hundredths must be an int")

    def celsius(self) -> float:
        """Return degrees Celsius. The only scaling of this value."""
        return self.hundredths / 100


def centi_celsius_from_degrees(degrees: float) -> int:
    """Wire hundredths for a setpoint command. Inverse of CentiCelsius.celsius."""
    return round(degrees * 100)


@dataclass(frozen=True)
class DeciVolt:
    """Tenths of a volt, as BatteryVoltage is reported."""

    tenths: int

    def __post_init__(self) -> None:
        if type(self.tenths) is not int:
            raise TypeError("tenths must be an int")

    def volts(self) -> float:
        return self.tenths / 10


@dataclass(frozen=True)
class IntCell:
    """One integer shadow cell.

    value is None when the key is absent or not an int. Zero is a reading.
    bool is rejected, because bool is a subclass of int and True == 1.
    """

    present: bool
    value: int | None

    def __post_init__(self) -> None:
        if self.value is None:
            return
        if not self.present or type(self.value) is not int:
            raise ValueError("cell value requires a present int")


@dataclass(frozen=True)
class KeypadLock:
    """LockKey. Locked only when the cell is the integer 1. Unlocked only when it is 0."""

    cell: IntCell

    def is_locked(self) -> bool | None:
        if self.cell.value == 1:
            return True
        if self.cell.value == 0:
            return False
        return None


@dataclass(frozen=True)
class ThermostatErrors:
    """Error01 through Error32.

    known is False when none of those keys exist. active lists the codes whose
    integer value is 1, in code order. A bool is not an active error.
    """

    known: bool
    active: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.active != tuple(sorted(self.active)):
            raise ValueError("active error codes must be sorted")
        if not self.known and self.active:
            raise ValueError("active errors require a reported error key")

    def is_on(self) -> bool | None:
        """Problem state. None when the thermostat reported no error keys."""
        if not self.known:
            return None
        return bool(self.active)


@dataclass(frozen=True)
class ClimateDiagnostics:
    """Battery, radio, keypad lock, and error keys from one property map.

    battery_level is the raw BatteryLevel cell. It is not a percentage and it
    is not BatteryVoltage in tenths of a volt.
    """

    battery_level: IntCell
    rssi_dbm: IntCell
    lqi: IntCell
    lock: KeypadLock
    errors: ThermostatErrors

    def __post_init__(self) -> None:
        for cell in (self.battery_level, self.rssi_dbm, self.lqi, self.lock.cell):
            if type(cell) is not IntCell:
                raise TypeError("diagnostic cells must be IntCell")
        if type(self.lock) is not KeypadLock or type(self.errors) is not ThermostatErrors:
            raise TypeError("lock and errors must be their domain types")


@dataclass(frozen=True)
class Hold:
    """HoldType. raw is None when the key is absent or not an int.

    present is False only when the key is absent. A present non-int is not standby
    and its preset slug is manual.
    """

    raw: int | None
    present: bool

    def __post_init__(self) -> None:
        if self.raw is not None and not self.present:
            raise ValueError("hold raw requires the key to be present")
        if self.raw is not None and type(self.raw) is not int:
            raise ValueError("hold raw must be an int")

    @property
    def is_standby(self) -> bool:
        return self.raw == _PRESET_RAW["away"]


@dataclass(frozen=True)
class SystemMode:
    """SystemMode. raw is None when the key is absent or not an int."""

    raw: int | None

    def __post_init__(self) -> None:
        if self.raw is not None and type(self.raw) is not int:
            raise TypeError("system mode raw must be an int")

    @property
    def is_off(self) -> bool:
        return self.raw == SYSTEM_MODE_OFF


@dataclass(frozen=True)
class ThermostatObservation:
    """One parsed thermostat shadow. observe and history cells are the only builders."""

    demand: Demand
    local_temperature: CentiCelsius | None
    heating_setpoint: CentiCelsius | None
    hold: Hold
    system_mode: SystemMode
    battery: DeciVolt | None

    def __post_init__(self) -> None:
        if type(self.demand) is not Demand:
            raise TypeError("demand must be Demand")
        for sample in (self.local_temperature, self.heating_setpoint):
            if sample is not None and type(sample) is not CentiCelsius:
                raise TypeError("temperatures must be CentiCelsius")
        if type(self.hold) is not Hold or type(self.system_mode) is not SystemMode:
            raise TypeError("hold and system_mode must be their domain types")
        if self.battery is not None and type(self.battery) is not DeciVolt:
            raise TypeError("battery must be DeciVolt")

    def hold_label(self) -> str | None:
        """Schedule, Manual Hold, Frost Protection, or Unknown (n). None if the key is absent."""
        if not self.hold.present:
            return None
        if self.hold.raw is None:
            return "Unknown"
        return _HOLD_LABELS.get(self.hold.raw, f"Unknown ({self.hold.raw})")

    def system_mode_label(self) -> str | None:
        """Off, Auto, Heat, or Unknown (n). None if the key is absent or not an int."""
        if self.system_mode.raw is None:
            return None
        return _SYSTEM_LABELS.get(self.system_mode.raw, f"Unknown ({self.system_mode.raw})")

    def preset_slug(self) -> str | None:
        """schedule, manual, away, or None when HoldType is absent.

        Any other present value, including a non-int, is manual.
        """
        if not self.hold.present:
            return None
        for slug, raw in _PRESET_RAW.items():
            if self.hold.raw == raw:
                return slug
        return "manual"


@dataclass(frozen=True)
class TemperatureMetric:
    """One statistics sensor. read returns the observation field, not a wire key."""

    slug: str
    name: str
    read: Callable[[ThermostatObservation], CentiCelsius | None]


@dataclass(frozen=True)
class MetricLabel:
    """Stable unique-id slug and the words appended to the device name."""

    slug: str
    name: str


def _read_local(observation: ThermostatObservation) -> CentiCelsius | None:
    return observation.local_temperature


def _read_setpoint(observation: ThermostatObservation) -> CentiCelsius | None:
    return observation.heating_setpoint


TEMPERATURE_METRICS: tuple[TemperatureMetric, ...] = (
    TemperatureMetric("local_temperature", "Temperature", _read_local),
    TemperatureMetric("heating_setpoint", "Heating setpoint", _read_setpoint),
)
RUNNING_STATE_METRIC = MetricLabel("running_state", "Running state")
PROBLEM_METRIC = MetricLabel("problem", "Problem")
LOCK_METRIC = MetricLabel("lock", "Keypad lock")


class DiagnosticKind(Enum):
    """RAW is an unscaled integer. SIGNAL_DBM is signal strength in dBm."""

    RAW = "raw"
    SIGNAL_DBM = "signal_dbm"


@dataclass(frozen=True)
class DiagnosticMetric:
    """One numeric diagnostic. read returns the cell, not a wire key."""

    slug: str
    name: str
    kind: DiagnosticKind
    read: Callable[[ClimateDiagnostics], IntCell]


def _read_battery_level(reading: ClimateDiagnostics) -> IntCell:
    return reading.battery_level


def _read_rssi(reading: ClimateDiagnostics) -> IntCell:
    return reading.rssi_dbm


def _read_lqi(reading: ClimateDiagnostics) -> IntCell:
    return reading.lqi


DIAGNOSTIC_METRICS: tuple[DiagnosticMetric, ...] = (
    DiagnosticMetric("battery_level", "Battery level", DiagnosticKind.RAW, _read_battery_level),
    DiagnosticMetric("signal_strength", "Signal strength", DiagnosticKind.SIGNAL_DBM, _read_rssi),
    DiagnosticMetric("link_quality", "Link quality", DiagnosticKind.RAW, _read_lqi),
)

_PRESET_RAW: dict[str, int] = {"schedule": 0, "manual": 2, "away": 7}
PRESET_SLUGS: tuple[str, ...] = tuple(_PRESET_RAW)

SYSTEM_MODE_OFF = 0
SYSTEM_MODE_HEAT = 4
_SYSTEM_LABELS: dict[int, str] = {SYSTEM_MODE_OFF: "Off", 1: "Auto", SYSTEM_MODE_HEAT: "Heat"}
_HOLD_LABELS: dict[int, str] = {
    _PRESET_RAW["schedule"]: "Schedule",
    _PRESET_RAW["manual"]: "Manual Hold",
    _PRESET_RAW["away"]: "Frost Protection",
}

_HOLD_WIRE = ("ep9:sIT600TH:SetHoldType", "ep9:sIT600TH:HoldType")
_SETPOINT_WIRE = ("ep9:sIT600TH:SetHeatingSetpoint_x100", "ep9:sIT600TH:HeatingSetpoint_x100")
_SYSTEM_WIRE = ("ep9:sIT600TH:SetSystemMode", "ep9:sIT600TH:SystemMode")
_READ_ONLY = {
    "running_state": "ep9:sIT600TH:RunningState",
    "local_temperature": "ep9:sIT600TH:LocalTemperature_x100",
    "battery": "ep9:sBasicS:BatteryVoltage",
}
_LOCK_WIRE = ("ep9:sIT600TH:SetLockKey", "ep9:sIT600TH:LockKey")
_BATTERY_LEVEL_KEY = "ep9:sIT600TH:BatteryLevel"
_RSSI_KEY = "ep9:sIT600I:LastMessageRSSI_d"
_LQI_KEY = "ep9:sIT600I:LastMessageLQI_d"
_THERMOSTAT_CLUSTER = "ep9:sIT600TH:"
_ERROR_CODE_LIMIT = 32


class ThermostatCommand:
    """Desired-property names the coordinator publishes. Reported names stay private."""

    HOLD = _HOLD_WIRE[0]
    SETPOINT = _SETPOINT_WIRE[0]
    SYSTEM_MODE = _SYSTEM_WIRE[0]
    LOCK = _LOCK_WIRE[0]


def hold_raw_for_preset(slug: str) -> int:
    """Return the HoldType integer for a preset slug. KeyError on an unknown slug."""
    return _PRESET_RAW[slug]


def desired_to_reported_thermostat() -> dict[str, str]:
    """Reported names for thermostat commands. state.py is the only caller."""
    return dict((_HOLD_WIRE, _SETPOINT_WIRE, _SYSTEM_WIRE, _LOCK_WIRE))


def decode_running_cell(value: Any, *, present: bool) -> Demand:
    """Classify one RunningState cell without knowing its property name.

    Absence is unreported. A present bool is unreadable, because bool is a
    subclass of int and True == 1 would otherwise count as heating.
    """
    if not present:
        return Demand.UNREPORTED
    if type(value) is not int:
        return Demand.UNREADABLE
    if value == 1:
        return Demand.HEATING
    return Demand.IDLE


def decode_x100_cell(value: Any, *, present: bool) -> CentiCelsius | None:
    """Hundredths of a degree, or None when the cell is missing or not an int.

    The integer 0 is 0°C. bool and float are not temperatures.
    """
    if not present or type(value) is not int:
        return None
    return CentiCelsius(value)


def observation_from_cells(
    *,
    running: Any,
    running_present: bool,
    local_x100: Any,
    local_present: bool,
    setpoint_x100: Any,
    setpoint_present: bool,
    hold: Any,
    hold_present: bool,
    system_mode: Any,
    system_mode_present: bool,
    battery_tenths: Any,
    battery_present: bool,
) -> ThermostatObservation:
    """Build an observation from raw cells. Callers do not pass property names."""
    tenths = _optional_int(battery_present, battery_tenths)
    return ThermostatObservation(
        demand=decode_running_cell(running, present=running_present),
        local_temperature=decode_x100_cell(local_x100, present=local_present),
        heating_setpoint=decode_x100_cell(setpoint_x100, present=setpoint_present),
        hold=_hold(hold_present, hold),
        system_mode=SystemMode(_optional_int(system_mode_present, system_mode)),
        battery=None if tenths is None else DeciVolt(tenths),
    )


def observe(properties: Mapping[str, Any]) -> ThermostatObservation | None:
    """Parse merged shadow properties.

    None iff properties is empty. A missing RunningState on a non-empty dict is
    Demand.UNREPORTED, not idle. A present non-int is Demand.UNREADABLE.
    """
    if not properties:
        return None
    running_present, running = _cell(properties, _READ_ONLY["running_state"])
    local_present, local = _cell(properties, _READ_ONLY["local_temperature"])
    setpoint_present, setpoint = _cell(properties, _SETPOINT_WIRE[1])
    hold_present, hold = _cell(properties, _HOLD_WIRE[1])
    system_present, system_mode = _cell(properties, _SYSTEM_WIRE[1])
    battery_present, battery = _cell(properties, _READ_ONLY["battery"])
    return observation_from_cells(
        running=running,
        running_present=running_present,
        local_x100=local,
        local_present=local_present,
        setpoint_x100=setpoint,
        setpoint_present=setpoint_present,
        hold=hold,
        hold_present=hold_present,
        system_mode=system_mode,
        system_mode_present=system_present,
        battery_tenths=battery,
        battery_present=battery_present,
    )


def heating_action(observation: ThermostatObservation | None) -> HeatingAction:
    """Climate action policy. Unknown demand stays unknown even when the mode is off."""
    if observation is None:
        return HeatingAction.UNKNOWN
    demand = observation.demand
    if demand is Demand.UNREPORTED or demand is Demand.UNREADABLE:
        return HeatingAction.UNKNOWN
    if observation.hold.is_standby or observation.system_mode.is_off:
        return HeatingAction.OFF
    if demand is Demand.HEATING:
        return HeatingAction.HEATING
    if demand is Demand.IDLE:
        return HeatingAction.IDLE
    raise RuntimeError(demand)


def _cell(properties: Mapping[str, Any], key: str) -> tuple[bool, Any]:
    if key not in properties:
        return False, None
    return True, properties[key]


def _optional_int(present: bool, value: Any) -> int | None:
    if present and type(value) is int:
        return value
    return None


def _hold(present: bool, value: Any) -> Hold:
    if not present:
        return Hold(raw=None, present=False)
    if type(value) is int:
        return Hold(raw=value, present=True)
    return Hold(raw=None, present=True)


def diagnostics(properties: Mapping[str, Any]) -> ClimateDiagnostics | None:
    """Parse battery, radio, lock, and error cells.

    None iff properties is empty. A missing key on a non-empty map is an absent
    cell, not a zero. BatteryLevel 0 is a raw level, not an absent battery.
    """
    if not properties:
        return None
    return ClimateDiagnostics(
        battery_level=_int_cell(properties, _BATTERY_LEVEL_KEY),
        rssi_dbm=_int_cell(properties, _RSSI_KEY),
        lqi=_int_cell(properties, _LQI_KEY),
        lock=KeypadLock(_int_cell(properties, _LOCK_WIRE[1])),
        errors=_errors(properties),
    )


def _int_cell(properties: Mapping[str, Any], key: str) -> IntCell:
    present, value = _cell(properties, key)
    if present and type(value) is int:
        return IntCell(present=True, value=value)
    return IntCell(present=present, value=None)


def _error_code(key: str) -> str | None:
    """Return Error01..Error32, or None when the key is a different property."""
    if not key.startswith(_THERMOSTAT_CLUSTER):
        return None
    name = key[len(_THERMOSTAT_CLUSTER) :]
    if len(name) != 7 or not name.startswith("Error"):
        return None
    suffix = name[5:]
    if not suffix.isdigit():
        return None
    number = int(suffix)
    if number < 1 or number > _ERROR_CODE_LIMIT:
        return None
    return name


def _errors(properties: Mapping[str, Any]) -> ThermostatErrors:
    active: list[str] = []
    known = False
    for key, value in properties.items():
        code = _error_code(key)
        if code is None:
            continue
        known = True
        if type(value) is int and value == 1:
            active.append(code)
    return ThermostatErrors(known=known, active=tuple(sorted(active)))
