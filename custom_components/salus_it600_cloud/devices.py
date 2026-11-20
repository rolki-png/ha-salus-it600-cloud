"""Classification of Salus devices."""

from __future__ import annotations

from typing import Any

from .heating import reports_thermostat

CLIMATE_MODELS = ("HTRP-RF", "TS600", "VS10", "VS20", "SQ610", "FC600")
SWITCH_MODELS = ("RS600", "SPE600", "SR600")


def is_climate_device(device: dict[str, Any]) -> bool:
    """Return whether the device is a thermostat.

    The shadow decides for models the name lists miss, such as it600ThermHW_AC.
    """
    return (
        (device.get("type") or "").lower() in ("thermostat", "climate")
        or (device.get("model") or "").upper().startswith(CLIMATE_MODELS)
        or "thermostat" in (device.get("name") or "").lower()
        or reports_thermostat(device.get("_shadow_properties") or {})
    )


def is_switch_device(device: dict[str, Any]) -> bool:
    """Return whether the device is a relay or a smart plug."""
    return (device.get("type") or "").lower() in ("switch", "relay") or (device.get("model") or "").upper().startswith(
        SWITCH_MODELS
    )


def is_user_rule(rule: dict[str, Any]) -> bool:
    """Return whether the OneTouch rule was created by the user."""
    name = rule.get("rule", {}).get("name", "")
    return bool(rule.get("rule_trigger_key")) and not name.startswith("_")
