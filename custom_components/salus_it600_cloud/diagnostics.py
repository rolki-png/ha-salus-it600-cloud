"""Diagnostics for the Salus iT600 Cloud integration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import SalusCloudCoordinator
from .devices import is_climate_device

# Exact config-entry keys. Shadow keys are matched separately, because they carry an endpoint prefix.
_ENTRY_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    "CertARN",
    "IdentityId",
    "LocalModeAccessCode",
    "NetworkPassword",
    "NetworkSSID",
    "WirelessAPpassword",
    "access_token",
    "id_token",
    "refresh_token",
    "session_token",
    "token",
}

# Property name after the last colon. Endpoint numbers differ per device, so the allowlist ignores them.
_THERMOSTAT_PROPERTIES = frozenset(
    {
        "AutoCoolingSetpoint_x100",
        "AutoHeatingSetpoint_x100",
        "BatteryLevel",
        "CloudySetpoint_x100",
        "CoolingSetpoint_x100",
        "CoolingSetpoint_x100_a",
        "HeatingSetpoint_x100",
        "HeatingSetpoint_x100_a",
        "HoldType",
        "HoldType_a",
        "LastMessageLQI_d",
        "LastMessageRSSI_d",
        "LocalTemperature_x100",
        "LockKey",
        "LockKey_a",
        "MaxCoolSetpoint_x100",
        "MaxHeatSetpoint_x100",
        "MaxHeatSetpoint_x100_a",
        "MinCoolSetpoint_x100",
        "MinCoolSetpoint_x100_a",
        "MinHeatSetpoint_x100",
        "OnlineState",
        "OnlineStatus_i",
        "RunningState",
        "SunnySetpoint_x100",
        "SystemMode",
        "SystemMode_a",
        "WiFiRSSI",
    }
)

_SECRET_MARKERS = (
    "password",
    "networkssid",
    "localmodeaccesscode",
    "certarn",
    "accesstoken",
    "idtoken",
    "refreshtoken",
    "sessiontoken",
    "identityid",
    "secretkey",
    "accesskey",
)
_SECRET_SEGMENTS = frozenset({"email", "token", "secret"})


def _key_is_secret(key: str) -> bool:
    segments = [part.casefold() for part in key.replace(":", "_").split("_") if part]
    if any(part in _SECRET_SEGMENTS for part in segments):
        return True
    folded = "".join(segments)
    return any(marker in folded for marker in _SECRET_MARKERS)


def _property_name(key: str) -> str:
    return key.rsplit(":", 1)[-1]


def _include_property(key: str) -> bool:
    if _key_is_secret(key):
        return False
    name = _property_name(key)
    return name in _THERMOSTAT_PROPERTIES or name.startswith("Error")


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _entry_int(entry: ConfigEntry, name: str) -> int | None:
    value = getattr(entry, name, None)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return None


def _secret_values(entry: ConfigEntry) -> tuple[str, ...]:
    found: list[str] = []
    data = _mapping(getattr(entry, "data", None))
    for key in (CONF_EMAIL, CONF_PASSWORD):
        value = data.get(key)
        if isinstance(value, str) and value:
            found.append(value)
    unique_id = getattr(entry, "unique_id", None)
    if isinstance(unique_id, str) and "@" in unique_id:
        found.append(unique_id)
    return tuple(dict.fromkeys(found))


def _scrub_text(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if text == secret:
            return REDACTED
        if secret in text and (len(secret) >= 8 or "@" in secret):
            text = text.replace(secret, REDACTED)
    return text


def _scrub(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return _scrub_text(value, secrets)
    if isinstance(value, list):
        return [_scrub(item, secrets) for item in value]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = _scrub_text(str(key), secrets)
            if _key_is_secret(str(key)):
                cleaned[key_text] = REDACTED
            else:
                cleaned[key_text] = _scrub(item, secrets)
        return cleaned
    return value


def _entry_diagnostics(entry: ConfigEntry) -> dict[str, Any]:
    return {
        "version": _entry_int(entry, "version"),
        "minor_version": _entry_int(entry, "minor_version"),
        "options": async_redact_data(_mapping(getattr(entry, "options", None)), _ENTRY_REDACT),
        "data": async_redact_data(_mapping(getattr(entry, "data", None)), _ENTRY_REDACT),
    }


def _coordinator_diagnostics(coordinator: SalusCloudCoordinator) -> dict[str, Any]:
    fresh = {
        device_id: bool(device.get("_fresh"))
        for device_id, device in sorted((coordinator.data or {}).items())
        if isinstance(device, dict)
    }
    info: dict[str, Any] = {
        "last_update_success": bool(coordinator.last_update_success),
        "push_available": coordinator.push_available if isinstance(coordinator.push_available, bool) else None,
        "push_denied": coordinator.push_denied,
        "fresh": fresh,
    }
    updated = getattr(coordinator, "last_update_success_time", None)
    if isinstance(updated, datetime):
        info["last_update_success_time"] = updated.isoformat()
    return info


def _devices(coordinator: SalusCloudCoordinator) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for device in (coordinator.data or {}).values():
        if not isinstance(device, dict) or not device.get("id"):
            continue
        devices.append(
            {
                "id": device.get("id"),
                "model": device.get("model"),
                "name": device.get("name"),
                "gateway_id": device.get("_gateway_id"),
            }
        )
    return sorted(devices, key=lambda item: str(item["id"]))


def _climate(coordinator: SalusCloudCoordinator) -> dict[str, dict[str, Any]]:
    climate: dict[str, dict[str, Any]] = {}
    for device_id, device in (coordinator.data or {}).items():
        if not isinstance(device, dict) or not is_climate_device(device):
            continue
        properties = device.get("_shadow_properties")
        if not isinstance(properties, Mapping):
            properties = {}
        selected: dict[str, Any] = {}
        for key, value in properties.items():
            if not isinstance(key, str) or not _include_property(key):
                continue
            copied = _json_value(value)
            if copied is None and value is not None:
                continue
            selected[key] = copied
        climate[str(device_id)] = {"properties": dict(sorted(selected.items()))}
    return dict(sorted(climate.items()))


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    secrets = _secret_values(entry)
    diagnostics: dict[str, Any] = {
        "entry": _entry_diagnostics(entry),
        "coordinator": None,
        "devices": [],
        "climate": {},
    }
    runtime = getattr(entry, "runtime_data", None)
    if isinstance(runtime, SalusCloudCoordinator):
        diagnostics["coordinator"] = _coordinator_diagnostics(runtime)
        diagnostics["devices"] = _devices(runtime)
        diagnostics["climate"] = _climate(runtime)
    return _scrub(diagnostics, secrets)
