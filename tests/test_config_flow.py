"""Tests for the Salus iT600 Cloud options flow."""

from unittest.mock import MagicMock

import pytest
from homeassistant.data_entry_flow import FlowResultType
import voluptuous as vol

from custom_components.salus_it600_cloud.config_flow import SalusOptionsFlow
from custom_components.salus_it600_cloud.const import (
    CONF_POLL_FAILURE_THRESHOLD,
    CONF_POST_COMMAND_REFRESH_DELAY,
    CONF_PUSH_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_SYNC_MODES,
    CONFIRM_REFRESH_DELAY_SECONDS,
    DEFAULT_POLL_FAILURE_THRESHOLD,
    PUSH_SCAN_INTERVAL_SECONDS,
    SCAN_INTERVAL_SECONDS,
)

OUT_OF_RANGE = (
    (CONF_SCAN_INTERVAL, 9),
    (CONF_SCAN_INTERVAL, 3601),
    (CONF_PUSH_SCAN_INTERVAL, 29),
    (CONF_PUSH_SCAN_INTERVAL, 3601),
    (CONF_POST_COMMAND_REFRESH_DELAY, 0),
    (CONF_POST_COMMAND_REFRESH_DELAY, 61),
    (CONF_POLL_FAILURE_THRESHOLD, 0),
    (CONF_POLL_FAILURE_THRESHOLD, 11),
)


def _flow(options: dict[str, object]) -> SalusOptionsFlow:
    flow = SalusOptionsFlow()
    entry = MagicMock()
    entry.options = options
    flow.hass = MagicMock()
    flow.handler = "entry-id"
    flow.hass.config_entries.async_get_known_entry.return_value = entry
    return flow


async def test_options_form_defaults_to_saved_or_builtin_values() -> None:
    """The form shows saved options, and the built-in timing defaults when none are saved."""

    empty = await _flow({}).async_step_init()
    assert empty["type"] == FlowResultType.FORM
    defaults = empty["data_schema"]({})
    assert defaults[CONF_SYNC_MODES] is False
    assert defaults[CONF_SCAN_INTERVAL] == SCAN_INTERVAL_SECONDS
    assert defaults[CONF_PUSH_SCAN_INTERVAL] == PUSH_SCAN_INTERVAL_SECONDS
    assert defaults[CONF_POST_COMMAND_REFRESH_DELAY] == CONFIRM_REFRESH_DELAY_SECONDS
    assert defaults[CONF_POLL_FAILURE_THRESHOLD] == DEFAULT_POLL_FAILURE_THRESHOLD

    saved = await _flow({CONF_SYNC_MODES: True, CONF_SCAN_INTERVAL: 45}).async_step_init()
    shown = saved["data_schema"]({})
    assert shown[CONF_SYNC_MODES] is True
    assert shown[CONF_SCAN_INTERVAL] == 45
    assert shown[CONF_PUSH_SCAN_INTERVAL] == PUSH_SCAN_INTERVAL_SECONDS


@pytest.mark.parametrize(("key", "value"), OUT_OF_RANGE)
async def test_options_schema_rejects_out_of_range(key: str, value: int) -> None:
    """Each timing option and the failure threshold stay inside their bounds."""

    form = await _flow({}).async_step_init()

    with pytest.raises(vol.Invalid):
        form["data_schema"]({key: value})


async def test_options_flow_stores_the_new_keys() -> None:
    """Submitting the form stores sync plus the four numeric options as integers."""

    flow = SalusOptionsFlow()
    result = await flow.async_step_init(
        {
            CONF_SYNC_MODES: True,
            CONF_SCAN_INTERVAL: 45.0,
            CONF_PUSH_SCAN_INTERVAL: 600.0,
            CONF_POST_COMMAND_REFRESH_DELAY: 4.0,
            CONF_POLL_FAILURE_THRESHOLD: 5.0,
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SYNC_MODES: True,
        CONF_SCAN_INTERVAL: 45,
        CONF_PUSH_SCAN_INTERVAL: 600,
        CONF_POST_COMMAND_REFRESH_DELAY: 4,
        CONF_POLL_FAILURE_THRESHOLD: 5,
    }
    for key in (
        CONF_SCAN_INTERVAL,
        CONF_PUSH_SCAN_INTERVAL,
        CONF_POST_COMMAND_REFRESH_DELAY,
        CONF_POLL_FAILURE_THRESHOLD,
    ):
        assert type(result["data"][key]) is int
