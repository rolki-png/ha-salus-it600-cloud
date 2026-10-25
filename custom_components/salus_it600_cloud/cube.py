"""Cube GraphQL history. Not imported by the coordinator.

Auth, the query document, and the response selection set are unproven.
This module names no host, header, or credential.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .heating import ThermostatObservation, observation_from_cells

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]


class CubeAuthUnproven(Exception):
    """The only session this change ships cannot authorize a request."""


class CubeQueryError(Exception):
    """The envelope contained GraphQL errors, or data was missing. No samples returned."""


@dataclass(frozen=True)
class HistoryWindow:
    """Identity of one history read. No cursor and no stored watermark."""

    device_code: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        """Reject a window that is not a complete, ordered, aware span."""
        if not self.device_code:
            raise ValueError("device_code is required")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("window bounds must be timezone-aware")
        if self.end < self.start:
            raise ValueError("window end is before start")


@dataclass(frozen=True)
class CubeRequest:
    """Unauthenticated GraphQL document. Transport will not accept this type."""

    document: str
    variables: Mapping[str, Json]


@dataclass(frozen=True)
class AuthorizedCubeRequest:
    """A request a session has accepted. The only type CubeTransport.post takes."""

    document: str
    variables: Mapping[str, Json]
    headers: Mapping[str, str]


class CubeTransport(Protocol):
    async def post(self, request: AuthorizedCubeRequest) -> Mapping[str, Json]:
        """POST one authorized document. Implementations own the URL and the HTTP session."""


class CubeSession(Protocol):
    async def authorize(self, request: CubeRequest) -> AuthorizedCubeRequest:
        """Return a request the transport may send, or raise."""


@dataclass(frozen=True)
class UnprovenCubeSession:
    """Shipped session. authorize does not return a request and stores no secret."""

    async def authorize(self, request: CubeRequest) -> AuthorizedCubeRequest:
        raise CubeAuthUnproven("Cube auth is not proven")


@dataclass(frozen=True)
class TimestampedObservation:
    at: datetime
    observation: ThermostatObservation


def timestamped_from_cells(
    *,
    at: datetime,
    running: Any,
    running_present: bool,
    local_x100: Any,
    local_present: bool,
    setpoint_x100: Any,
    setpoint_present: bool,
    hold: Any = None,
    hold_present: bool = False,
    system_mode: Any = None,
    system_mode_present: bool = False,
    battery_tenths: Any = None,
    battery_present: bool = False,
) -> TimestampedObservation:
    """Build one history sample from cells. This does not accept a shadow property map."""
    if at.tzinfo is None:
        raise ValueError("history timestamp must be timezone-aware")
    return TimestampedObservation(
        at=at,
        observation=observation_from_cells(
            running=running,
            running_present=running_present,
            local_x100=local_x100,
            local_present=local_present,
            setpoint_x100=setpoint_x100,
            setpoint_present=setpoint_present,
            hold=hold,
            hold_present=hold_present,
            system_mode=system_mode,
            system_mode_present=system_mode_present,
            battery_tenths=battery_tenths,
            battery_present=battery_present,
        ),
    )


class CubeHistory:
    """One-shot history read. Not a DataUpdateCoordinator and not cached."""

    def __init__(self, transport: CubeTransport, session: CubeSession) -> None:
        self._transport = transport
        self._session = session

    async def fetch(self, window: HistoryWindow) -> tuple[TimestampedObservation, ...]:
        """Return observations for the window.

        UnprovenCubeSession raises before a document is built and before transport.post.
        Any other session builds the document next. Until that document exists, fetch
        raises NotImplementedError and still does not post.
        """
        if isinstance(self._session, UnprovenCubeSession):
            raise CubeAuthUnproven("Cube auth is not proven")
        request = _history_request(window)
        authorized = await self._session.authorize(request)
        payload = await self._transport.post(authorized)
        return _parse_history_payload(payload)


def _history_request(window: HistoryWindow) -> CubeRequest:
    """Build the GraphQL document. Body stays unimplemented until a capture exists."""
    raise NotImplementedError("Cube query document and variable names are unproven")


def _parse_history_payload(payload: Mapping[str, Json]) -> tuple[TimestampedObservation, ...]:
    """Parse a captured payload into observations.

    An envelope with errors, or with no data object, raises CubeQueryError before
    any row is decoded. A clean envelope still cannot be decoded: the selection
    set is unproven, and rows must go through timestamped_from_cells rather than
    a forged shadow map.
    """
    if payload.get("errors"):
        raise CubeQueryError("GraphQL response contained errors")
    if not isinstance(payload.get("data"), Mapping):
        raise CubeQueryError("GraphQL response had no data")
    raise NotImplementedError("Cube response selection set is unproven")
