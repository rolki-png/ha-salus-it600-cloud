"""Translation files name the same entities the platforms expose."""

import json
from pathlib import Path

from custom_components.salus_it600_cloud.heating import PRESET_SLUGS

ROOT = Path(__file__).parents[1] / "custom_components" / "salus_it600_cloud"

SENSOR_NAMES = {
    "battery_level": "Battery level",
    "heating_setpoint": "Heating setpoint",
    "link_quality": "Link quality",
    "signal_strength": "Signal strength",
    "temperature": "Temperature",
}
PRESET_NAMES = {
    "away": "Frost protection",
    "manual": "Manual",
    "schedule": "Schedule",
}
PRESET_ICONS = {
    "away": "mdi:snowflake",
    "manual": "mdi:hand-back-right",
    "schedule": "mdi:calendar",
}


def _load(name: str) -> dict:
    return json.loads((ROOT / name).read_text())


def _paths(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return set()
    found: set[str] = set()
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        found.add(path)
        found.update(_paths(child, path))
    return found


def test_english_catalog_names_child_entities_and_presets() -> None:
    """strings.json and translations/en.json carry the same entity labels."""

    strings = _load("strings.json")
    english = _load("translations/en.json")

    assert strings["entity"] == english["entity"]
    assert {key: item["name"] for key, item in strings["entity"]["sensor"].items()} == SENSOR_NAMES
    binary = strings["entity"]["binary_sensor"]
    assert binary["running_state"]["name"] == "Running state"
    assert binary["running_state"]["state"] == {"off": "Idle", "on": "Heating"}
    assert binary["problem"]["name"] == "Problem"
    assert strings["entity"]["lock"]["keypad_lock"]["name"] == "Keypad lock"
    presets = strings["entity"]["climate"]["thermostat"]["state_attributes"]["preset_mode"]["state"]
    assert presets == PRESET_NAMES
    assert set(presets) == set(PRESET_SLUGS)


def test_czech_catalog_has_the_same_entity_keys() -> None:
    """cs.json covers every new entity key, including preset states."""

    strings = _load("strings.json")
    czech = _load("translations/cs.json")

    assert _paths(czech["entity"]) == _paths(strings["entity"])
    assert czech["entity"]["sensor"]["temperature"]["name"] == "Teplota"
    assert czech["entity"]["climate"]["thermostat"]["state_attributes"]["preset_mode"]["state"]["away"] == (
        "Protimrazová ochrana"
    )


def test_preset_icons_cover_every_preset() -> None:
    """Preset icons follow the climate translation key."""

    icons = _load("icons.json")
    state = icons["entity"]["climate"]["thermostat"]["state_attributes"]["preset_mode"]["state"]

    assert set(icons["entity"]) == {"climate"}
    assert state == PRESET_ICONS
    assert set(state) == set(PRESET_SLUGS)
