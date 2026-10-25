"""Cube history refuses to talk to the network until auth and the query are proven."""

from datetime import datetime, timezone
from typing import Any

import pytest

from custom_components.salus_it600_cloud.cube import (
    AuthorizedCubeRequest,
    CubeAuthUnproven,
    CubeHistory,
    CubeQueryError,
    CubeRequest,
    HistoryWindow,
    UnprovenCubeSession,
    _parse_history_payload,
    timestamped_from_cells,
)
from custom_components.salus_it600_cloud.heating import Demand


class _Transport:
    def __init__(self) -> None:
        self.posts = 0

    async def post(self, request: AuthorizedCubeRequest) -> dict[str, Any]:
        self.posts += 1
        return {}


class _Session:
    def __init__(self) -> None:
        self.authorized = 0

    async def authorize(self, request: CubeRequest) -> AuthorizedCubeRequest:
        self.authorized += 1
        return AuthorizedCubeRequest(request.document, request.variables, {})


def _window() -> HistoryWindow:
    return HistoryWindow(
        device_code="device",
        start=datetime(2026, 10, 1, tzinfo=timezone.utc),
        end=datetime(2026, 10, 2, tzinfo=timezone.utc),
    )


async def test_unproven_session_raises_before_post() -> None:
    transport = _Transport()

    with pytest.raises(CubeAuthUnproven):
        await CubeHistory(transport, UnprovenCubeSession()).fetch(_window())

    assert transport.posts == 0


async def test_unproven_session_authorize_does_not_return_a_request() -> None:
    with pytest.raises(CubeAuthUnproven):
        await UnprovenCubeSession().authorize(CubeRequest("query", {}))


async def test_proven_session_still_does_not_post_without_a_document() -> None:
    transport = _Transport()
    session = _Session()

    with pytest.raises(NotImplementedError, match="query document"):
        await CubeHistory(transport, session).fetch(_window())

    assert transport.posts == 0
    assert session.authorized == 0


def test_graphql_errors_are_rejected_before_a_selection_set() -> None:
    with pytest.raises(CubeQueryError):
        _parse_history_payload({"errors": [{"message": "denied"}], "data": {"rows": [{"running": 1}]}})
    with pytest.raises(CubeQueryError):
        _parse_history_payload({"data": None})
    with pytest.raises(NotImplementedError, match="selection set"):
        _parse_history_payload({"data": {}})


def test_history_cells_decode_without_a_shadow_map() -> None:
    """A bool running cell is unreadable. History does not rebuild property names to get there."""

    sample = timestamped_from_cells(
        at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        running=True,
        running_present=True,
        local_x100=0,
        local_present=True,
        setpoint_x100=2100,
        setpoint_present=True,
    )

    assert sample.observation.demand is Demand.UNREADABLE
    assert sample.observation.demand.is_on() is None
    assert sample.observation.local_temperature.celsius() == 0.0
    assert sample.observation.heating_setpoint.celsius() == 21.0


def test_history_timestamp_must_be_aware() -> None:
    with pytest.raises(ValueError):
        timestamped_from_cells(
            at=datetime(2026, 10, 1),
            running=0,
            running_present=True,
            local_x100=None,
            local_present=False,
            setpoint_x100=None,
            setpoint_present=False,
        )


def test_window_requires_an_ordered_aware_span() -> None:
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 2, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        HistoryWindow("device", datetime(2026, 10, 1), end)
    with pytest.raises(ValueError):
        HistoryWindow("device", end, start)
    with pytest.raises(ValueError):
        HistoryWindow("", start, end)
