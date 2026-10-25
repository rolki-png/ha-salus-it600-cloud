"""Tests for the thermostat keypad lock."""

from unittest.mock import MagicMock, patch

from homeassistant.const import EntityCategory

from custom_components.salus_it600_cloud import lock
from custom_components.salus_it600_cloud.lock import SalusThermostatLock

from . import fixtures
from .helpers import CALL_LATER, FakeApi, create_coordinator

LOCK_KEY = "ep9:sIT600TH:LockKey"


async def _coordinator_with(lock_key: object | None):
    api = FakeApi()
    shadow = fixtures.thermostat_shadow(hold_type=0)
    if lock_key is not None:
        shadow["state"]["reported"]["11"]["properties"][LOCK_KEY] = lock_key
    api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    return await create_coordinator(api)


def _uid(device_id: str) -> str:
    return f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{device_id}_lock"


async def _entities(coordinator: object) -> dict[str, SalusThermostatLock]:
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    await lock.async_setup_entry(MagicMock(), entry, add_entities)
    if not add_entities.called:
        return {}
    return {entity.unique_id: entity for entity in add_entities.call_args.args[0]}


async def test_setup_creates_a_lock_when_lock_key_is_present_including_zero() -> None:
    """LockKey 0 is unlocked and still creates the entity. A thermostat without the key gets none."""

    coordinator, _, _ = await _coordinator_with(0)
    entities = await _entities(coordinator)
    entity = entities[_uid(fixtures.THERMOSTAT_ID)]

    assert isinstance(entity, SalusThermostatLock)
    assert entity.is_locked is False
    assert entity.entity_category is EntityCategory.CONFIG
    assert entity.name == "Apartmán A Termostat pokoj Keypad lock"
    assert entity.unique_id == _uid(fixtures.THERMOSTAT_ID)
    assert entity.translation_key == "keypad_lock"
    assert entity.has_entity_name is False
    assert _uid(fixtures.THERMOSTAT_2_ID) not in entities
    assert _uid(fixtures.RELAY_ID) not in entities


async def test_integer_one_is_locked() -> None:
    coordinator, _, _ = await _coordinator_with(1)
    entities = await _entities(coordinator)

    assert entities[_uid(fixtures.THERMOSTAT_ID)].is_locked is True


async def test_bool_and_other_integers_are_unknown() -> None:
    """True must not count as locked, because True == 1."""

    for value in (True, 5):
        coordinator, _, _ = await _coordinator_with(value)
        entity = (await _entities(coordinator))[_uid(fixtures.THERMOSTAT_ID)]
        assert entity.is_locked is None


async def test_missing_lock_key_creates_no_entity() -> None:
    coordinator, _, _ = await _coordinator_with(None)
    entities = await _entities(coordinator)

    assert entities == {}


async def test_lock_publishes_set_lock_key_and_shows_it_immediately() -> None:
    """The command is per thermostat. The pending overlay reports locked before the device confirms."""

    coordinator, connection, _ = await create_coordinator(sync=True)
    shadow = fixtures.thermostat_shadow(hold_type=0)
    shadow["state"]["reported"]["11"]["properties"][LOCK_KEY] = 0
    coordinator.api.shadows[fixtures.THERMOSTAT_CODE] = shadow
    coordinator.data = await coordinator._async_update_data()
    entity = (await _entities(coordinator))[_uid(fixtures.THERMOSTAT_ID)]
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    with patch(CALL_LATER):
        await entity.async_lock()

    assert connection.published == [(fixtures.THERMOSTAT_CODE, "11", {"ep9:sIT600TH:SetLockKey": 1})]
    assert type(connection.published[0][2]["ep9:sIT600TH:SetLockKey"]) is int
    assert entity.is_locked is True


async def test_unlock_publishes_zero() -> None:
    coordinator, connection, _ = await _coordinator_with(1)
    entity = (await _entities(coordinator))[_uid(fixtures.THERMOSTAT_ID)]
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()

    with patch(CALL_LATER):
        await entity.async_unlock()

    assert connection.published == [(fixtures.THERMOSTAT_CODE, "11", {"ep9:sIT600TH:SetLockKey": 0})]
    assert entity.is_locked is False


async def test_lock_key_leaving_is_unknown() -> None:
    coordinator, _, _ = await _coordinator_with(1)
    entity = (await _entities(coordinator))[_uid(fixtures.THERMOSTAT_ID)]
    entity.hass = MagicMock()
    del coordinator.data[fixtures.THERMOSTAT_ID]["_shadow_properties"][LOCK_KEY]

    assert entity.is_locked is None
    assert entity.available is True
