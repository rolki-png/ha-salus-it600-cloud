"""Tests for config entry diagnostics."""

import json
from unittest.mock import MagicMock

from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from custom_components.salus_it600_cloud.const import CONF_SYNC_MODES
from custom_components.salus_it600_cloud.diagnostics import async_get_config_entry_diagnostics

from . import fixtures
from .helpers import FakeApi, create_coordinator

PASSWORD = "super-secret-password"
EMAIL = "person@example.com"
NETWORK_PASSWORD = "gateway-wifi-secret"


def _entry(coordinator: object | None) -> MagicMock:
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.version = 1
    entry.minor_version = 1
    entry.options = {CONF_SYNC_MODES: True}
    entry.data = {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    entry.unique_id = EMAIL
    entry.title = f"Salus iT600 Cloud ({EMAIL})"
    return entry


async def test_diagnostics_redacts_secrets_and_keeps_running_state() -> None:
    """Downloaded diagnostics keep RunningState and leave out the password and gateway network password."""

    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=2)
    properties = shadow["state"]["reported"]["11"]["properties"]
    properties["ep9:sIT600TH:RunningState"] = 1
    properties["ep0:sGateway:NetworkPassword"] = NETWORK_PASSWORD
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator, connection, _ = await create_coordinator(api)
    connection.push_denied = True
    entry = _entry(coordinator)

    result = await async_get_config_entry_diagnostics(MagicMock(), entry)
    blob = json.dumps(result)

    assert PASSWORD not in blob
    assert EMAIL not in blob
    assert fixtures.GUEST_EMAIL not in blob
    assert NETWORK_PASSWORD not in blob
    assert "NetworkPassword" not in blob
    assert entry.data[CONF_PASSWORD] == PASSWORD
    assert result["entry"]["data"]["password"] == REDACTED
    assert result["entry"]["data"]["email"] == REDACTED
    assert result["entry"]["version"] == 1
    assert result["entry"]["minor_version"] == 1
    assert result["entry"]["options"] == {CONF_SYNC_MODES: True}
    assert {item["id"] for item in result["devices"]} == {
        fixtures.THERMOSTAT_ID,
        fixtures.THERMOSTAT_2_ID,
        fixtures.RELAY_ID,
        fixtures.GATEWAY_ID,
    }
    assert next(item for item in result["devices"] if item["id"] == fixtures.THERMOSTAT_ID) == {
        "id": fixtures.THERMOSTAT_ID,
        "model": "SQ610RF",
        "name": "Termostat pokoj",
        "gateway_id": fixtures.GATEWAY_ID,
    }
    assert set(result["climate"]) == {fixtures.THERMOSTAT_ID, fixtures.THERMOSTAT_2_ID}
    assert result["climate"][fixtures.THERMOSTAT_ID]["properties"]["ep9:sIT600TH:RunningState"] == 1
    assert result["climate"][fixtures.THERMOSTAT_2_ID]["properties"]["ep9:sIT600TH:RunningState"] == 0
    assert "BatteryVoltage" not in blob
    assert "sOnOffS" not in blob
    assert result["coordinator"]["push_denied"] is True
    assert result["coordinator"]["fresh"][fixtures.THERMOSTAT_ID] is True
    assert result["coordinator"]["fresh"][fixtures.GATEWAY_ID] is False


async def test_diagnostics_without_runtime_still_redacts_password() -> None:
    """An entry that has not loaded still redacts the stored password."""

    entry = _entry(None)
    result = await async_get_config_entry_diagnostics(MagicMock(), entry)

    assert PASSWORD not in json.dumps(result)
    assert result["entry"]["data"]["password"] == REDACTED
    assert result["coordinator"] is None
    assert result["devices"] == []
    assert result["climate"] == {}
