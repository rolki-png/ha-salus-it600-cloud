# Supported devices

One EU Premium account's device shadow, read in October 2026, is the inventory below. The entities are what this integration creates.

## Thermostat

The account shadow has a thermostat on endpoint 9, cluster `sIT600TH`. That is the SQ610 climate device.

The climate entity offers heat and off. Presets are schedule, manual, and frost protection. The target temperature is the heating setpoint. A slider drag waits 0.3 seconds, then the integration writes the last value. The current temperature comes from `LocalTemperature_x100`. The minimum and maximum follow `MinHeatSetpoint_x100` and `MaxHeatSetpoint_x100` when those cells are integers. A missing minimum stays at 5°C. A missing maximum stays at 35°C.

Cool stays disabled. `SystemMode` is in the shadow. The integer that means cool is not proven, so the entity does not offer cool.

### Sensors

The thermostat gets these sensors when the matching shadow cell is present.

- Temperature, from the room reading.
- Heating setpoint.
- Cooling setpoint, only when `CoolingControl` is the integer 1 or `CoolingSetpoint_x100` is present. The sensor does not turn on cool mode.
- Battery level, the raw `BatteryLevel` integer. There is no percent unit, so a reported 0 stays 0.
- Signal strength, `LastMessageRSSI_d`, in dBm.
- Link quality, `LastMessageLQI_d`, as a raw integer.

### Binary sensors

- Running state, from `RunningState`. The integer 1 means heating. Any other integer means idle. A missing or non-integer value stays unknown.
- Problem. The sensor exists when the thermostat has reported `Error01` through `Error32`. It is on when any of those values is the integer 1. The `error_codes` attribute lists those codes.

### Lock

Keypad lock exists when `LockKey` is present. Lock and unlock write `SetLockKey`.

## Humidity

The account shadow has no humidity property. The integration does not create a humidity sensor.

## Wiring centre

Endpoint 8 reports cluster `sIT600WC`. The shadow includes wiring-centre errors `Error10` through `Error20`, `Error26` through `Error29`, and `ErrorCodeWC_d`. The integration creates no entities for those cells. The thermostat problem sensor ignores them.

## Boiler receiver

Endpoint 7 reports `sIT600I:RelayStatus`, plus `Mode` and the link counters `LastMessageLQI_d` and `LastMessageRSSI_d`. A switch entity reads `ep9:sOnOffS:OnOff` on a device whose type is switch or relay, or whose model starts with RS600, SPE600, or SR600. `RelayStatus` on endpoint 7 does not become a switch.

## Other devices the code still creates

The climate check also accepts model prefixes HTRP-RF, TS600, VS10, VS20, SQ610, and FC600. This account's reported thermostat cluster is `sIT600TH`.

When the device list contains them, the integration also creates these entities.

- A switch for RS600, SPE600, or SR600.
- A binary sensor for a door, a window, motion, occupancy, or a WLS contact. A WLS contact uses the moisture class. A window contact is a window, and a door contact is a door. A contact with no state field stays unknown.
- A button for a OneTouch rule you created. A rule whose name starts with `_` is skipped.
- A temperature sensor for a device whose type is a temperature sensor.

The gateway is a Home Assistant device. Its network settings and AWS IoT properties are not entities.
