"""Devices and OneTouch rules that show up after the first coordinator snapshot."""

from unittest.mock import MagicMock

from custom_components.salus_it600_cloud import async_remove_config_entry_device, button, climate
from custom_components.salus_it600_cloud.climate import SalusCloudClimate
from custom_components.salus_it600_cloud.const import DOMAIN
from custom_components.salus_it600_cloud.coordinator import SalusCloudCoordinator

from . import fixtures
from .helpers import create_coordinator

NEW_THERMOSTAT_ID = "20000000-0000-4000-8000-000000000099"
NEWER_THERMOSTAT_ID = "20000000-0000-4000-8000-000000000098"
NEW_RULE_ID = "40000000-0000-4000-8000-000000000099"


def _thermostat(device_id: str) -> dict[str, object]:
    return {
        "id": device_id,
        "name": "Termostat novy",
        "model": "SQ610RF",
        "_gateway_id": fixtures.GATEWAY_ID,
        "_shadow_properties": {},
        "_fresh": True,
    }


def _setup_climate(coordinator: SalusCloudCoordinator) -> tuple[MagicMock, MagicMock]:
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    return entry, add_entities


def _device(*identifiers: str) -> MagicMock:
    device = MagicMock()
    device.identifiers = {(DOMAIN, identifier) for identifier in identifiers}
    return device


async def test_second_update_adds_a_new_thermostat_only() -> None:
    """A thermostat that appears after setup becomes a climate entity, and known ones are not created again."""

    coordinator, _, _ = await create_coordinator()
    entry, add_entities = _setup_climate(coordinator)
    await climate.async_setup_entry(MagicMock(), entry, add_entities)
    first_ids = [entity.unique_id for entity in add_entities.call_args.args[0]]

    updated = dict(coordinator.data)
    updated[NEW_THERMOSTAT_ID] = _thermostat(NEW_THERMOSTAT_ID)
    coordinator.async_set_updated_data(updated)

    added = add_entities.call_args.args[0]
    assert add_entities.call_count == 2
    assert len(added) == 1
    assert isinstance(added[0], SalusCloudClimate)
    assert added[0].unique_id == f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{NEW_THERMOSTAT_ID}"
    assert added[0].unique_id not in first_ids

    coordinator.async_set_updated_data({})
    assert add_entities.call_count == 2

    coordinator.async_set_updated_data(updated)
    assert add_entities.call_count == 2

    with_another = dict(updated)
    with_another[NEWER_THERMOSTAT_ID] = _thermostat(NEWER_THERMOSTAT_ID)
    coordinator.async_set_updated_data(with_another)

    assert add_entities.call_count == 3
    assert [entity.unique_id for entity in add_entities.call_args.args[0]] == [
        f"salus_it600_cloud_{fixtures.GATEWAY_ID}_{NEWER_THERMOSTAT_ID}"
    ]


async def test_second_update_adds_a_new_user_rule_button() -> None:
    """A user OneTouch rule that appears later gets a button. Generated rules still do not."""

    coordinator, _, _ = await create_coordinator()
    entry = MagicMock()
    entry.runtime_data = coordinator
    add_entities = MagicMock()
    await button.async_setup_entry(MagicMock(), entry, add_entities)

    coordinator.rules.extend(
        [
            {
                "id": NEW_RULE_ID,
                "rule_trigger_key": "ruleTriggerKey-new",
                "_gateway_id": fixtures.GATEWAY_ID,
                "rule": {"name": "Vecer"},
            },
            {
                "id": "40000000-0000-4000-8000-000000000098",
                "rule_trigger_key": "ruleTriggerKey-generated",
                "_gateway_id": fixtures.GATEWAY_ID,
                "rule": {"name": "_generated"},
            },
        ]
    )
    coordinator.async_set_updated_data(dict(coordinator.data))

    assert add_entities.call_count == 2
    added = add_entities.call_args.args[0]
    assert [entity.unique_id for entity in added] == [
        f"salus_it600_cloud_{fixtures.GATEWAY_ID}_onetouch_{NEW_RULE_ID}"
    ]


async def test_device_removal_follows_the_snapshot() -> None:
    """Home Assistant can delete a device the snapshot omits, and cannot delete one it still lists.

    An empty snapshot keeps every device. It is not evidence that the devices left.
    """

    coordinator, _, _ = await create_coordinator()
    entry = MagicMock()
    entry.runtime_data = coordinator
    hass = MagicMock()

    assert await async_remove_config_entry_device(hass, entry, _device(fixtures.THERMOSTAT_ID)) is False
    assert await async_remove_config_entry_device(hass, entry, _device(fixtures.GATEWAY_ID)) is False
    assert (
        await async_remove_config_entry_device(hass, entry, _device(f"{fixtures.GATEWAY_ID}_onetouch_rules")) is False
    )

    remaining = dict(coordinator.data)
    del remaining[fixtures.THERMOSTAT_ID]
    coordinator.data = remaining
    assert await async_remove_config_entry_device(hass, entry, _device(fixtures.THERMOSTAT_ID)) is True
    assert await async_remove_config_entry_device(hass, entry, _device(fixtures.RELAY_ID)) is False

    without_gateway = {device_id: device for device_id, device in remaining.items() if device_id != fixtures.GATEWAY_ID}
    coordinator.data = without_gateway
    assert await async_remove_config_entry_device(hass, entry, _device(fixtures.GATEWAY_ID)) is False

    coordinator.rules[:] = [rule for rule in coordinator.rules if rule.get("id") != fixtures.RULE_ID]
    assert (
        await async_remove_config_entry_device(hass, entry, _device(f"{fixtures.GATEWAY_ID}_onetouch_rules")) is True
    )

    coordinator.data = {}
    assert await async_remove_config_entry_device(hass, entry, _device(fixtures.THERMOSTAT_ID)) is False

    coordinator.data = None
    assert await async_remove_config_entry_device(hass, entry, _device(fixtures.THERMOSTAT_ID)) is False
