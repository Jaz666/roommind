"""Persistence, API, room assignment, and override tests for reusable schedules."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.const import DOMAIN
from custom_components.roommind.store import RoomMindStore
from custom_components.roommind.utils.reusable_schedule import validate_schedule
from custom_components.roommind.websocket_api import (
    websocket_delete_schedule,
    websocket_list_rooms,
    websocket_list_schedules,
    websocket_override_set,
    websocket_save_room,
    websocket_save_schedule,
)
from tests.utils.test_reusable_schedule import week


@pytest.fixture
async def scheduled_store(hass, store):
    await store.async_load()
    for area_id in ("bedroom", "guest", "living"):
        await store.async_save_room(area_id, {"schedules": [{"entity_id": f"schedule.{area_id}"}]})
    hass.data[DOMAIN] = {"store": store}
    return store


async def test_save_link_edit_unassign_and_reload(hass, scheduled_store):
    store = scheduled_store
    schedule = validate_schedule("Bedrooms", week())
    await store.async_save_schedule("bedrooms", schedule, ["bedroom", "guest"], 0)
    assert store.get_room("bedroom")["roommind_schedule_id"] == "bedrooms"
    assert store.get_room("living")["roommind_schedule_id"] == ""
    returned = store.get_schedules()
    returned["bedrooms"]["days"]["monday"][0]["data"]["heat_temperature"] = 30
    assert store.get_schedules()["bedrooms"]["days"]["monday"][0]["data"]["heat_temperature"] == 19
    schedule["days"]["monday"][0]["data"]["heat_temperature"] = 18
    await store.async_save_schedule("bedrooms", schedule, ["bedroom"], 1)
    assert store.get_room("guest")["roommind_schedule_id"] == ""
    assert store.get_room("guest")["schedules"] == [{"entity_id": "schedule.guest"}]
    persisted = store._store.async_save.call_args.args[0]
    reloaded = RoomMindStore(hass)
    reloaded._store.async_load = AsyncMock(return_value=persisted)
    await reloaded.async_load()
    assert reloaded.get_schedules()["bedrooms"]["revision"] == 2
    assert reloaded.get_room("bedroom")["roommind_schedule_id"] == "bedrooms"
    assert reloaded.get_schedules()["bedrooms"]["days"]["monday"][0]["data"]["heat_temperature"] == 18


async def test_stale_edit_and_invalid_rooms_are_atomic(scheduled_store):
    store = scheduled_store
    schedule = validate_schedule("Bedrooms", week())
    await store.async_save_schedule("bedrooms", schedule, ["bedroom"], 0)
    before = store.get_rooms(), store.get_schedules()
    with pytest.raises(ValueError, match="another window"):
        await store.async_save_schedule("bedrooms", schedule, ["guest"], 0)
    with pytest.raises(ValueError, match="indoor"):
        await store.async_save_schedule("bedrooms", schedule, ["missing"], 1)
    assert (store.get_rooms(), store.get_schedules()) == before
    with pytest.raises(ValueError, match="Unassign"):
        await store.async_delete_schedule("bedrooms", 1)
    await store.async_save_schedule("bedrooms", schedule, [], 1)
    await store.async_delete_schedule("bedrooms", 2)
    assert store.get_schedules() == {}


async def test_move_room_between_linked_schedules(scheduled_store):
    store = scheduled_store
    await store.async_save_schedule("a", validate_schedule("A", week()), ["bedroom", "guest"], 0)
    await store.async_save_schedule("b", validate_schedule("B", week()), ["bedroom"], 0)
    assert store.get_room("bedroom")["roommind_schedule_id"] == "b"
    assert store.get_room("guest")["roommind_schedule_id"] == "a"


async def test_websocket_save_list_summary_assign_and_delete(hass, scheduled_store):
    conn = MagicMock()
    msg = {
        "id": 1,
        "type": "roommind/schedules/save",
        "name": "Bedrooms",
        "days": week(),
        "area_ids": ["bedroom"],
        "revision": 0,
    }
    await websocket_save_schedule.__wrapped__(hass, conn, msg)
    conn.send_error.assert_not_called()
    saved = conn.send_result.call_args.args[1]["schedule"]
    sid = saved["id"]
    await websocket_list_schedules.__wrapped__(hass, conn, {"id": 2})
    assert conn.send_result.call_args.args[1]["schedules"][sid]["area_ids"] == ["bedroom"]
    with patch(
        "custom_components.roommind.websocket_api.time.time",
        return_value=datetime(2026, 7, 6, 8, tzinfo=dt_util.get_default_time_zone()).timestamp(),
    ):
        await websocket_list_rooms.__wrapped__(hass, conn, {"id": 3})
    result = conn.send_result.call_args.args[1]
    assert result["rooms"]["bedroom"]["roommind_schedule"]["targets"]["heat_temperature"] == 20
    assert result["reusable_schedules"] == [{"id": sid, "name": "Bedrooms"}]
    await websocket_save_room.__wrapped__(hass, conn, {"id": 4, "area_id": "guest", "roommind_schedule_id": sid})
    assert scheduled_store.get_room("guest")["roommind_schedule_id"] == sid
    await websocket_delete_schedule.__wrapped__(hass, conn, {"id": 5, "schedule_id": sid, "revision": 1})
    assert conn.send_error.call_args.args[1] == "invalid_schedule"


@pytest.mark.parametrize("changes", [{"days": {}}, {"area_ids": ["missing"]}, {"name": ""}, {"schedule_id": "deleted"}])
async def test_websocket_rejects_bad_save_without_assigning(hass, scheduled_store, changes):
    conn = MagicMock()
    before = scheduled_store.get_rooms()
    msg = {"id": 1, "name": "Bedrooms", "days": week(), "area_ids": ["bedroom"], "revision": 0, **changes}
    await websocket_save_schedule.__wrapped__(hass, conn, msg)
    conn.send_error.assert_called_once()
    assert scheduled_store.get_rooms() == before
    assert scheduled_store.get_schedules() == {}


async def test_missing_room_schedule_is_rejected_and_reported(hass, scheduled_store):
    conn = MagicMock()
    await websocket_save_room.__wrapped__(
        hass, conn, {"id": 1, "area_id": "bedroom", "roommind_schedule_id": "missing"}
    )
    conn.send_error.assert_called_once()
    # Simulate an inconsistent restored storage file.
    await scheduled_store.async_update_room("bedroom", {"roommind_schedule_id": "missing"})
    await websocket_list_rooms.__wrapped__(hass, conn, {"id": 2})
    assert conn.send_result.call_args.args[1]["rooms"]["bedroom"]["roommind_schedule_missing"] is True


async def test_override_until_next_schedule_change(hass, scheduled_store):
    store = scheduled_store
    await store.async_save_schedule("bedrooms", validate_schedule("Bedrooms", week()), ["bedroom"], 0)
    now = datetime(2026, 7, 6, 21, tzinfo=dt_util.get_default_time_zone()).timestamp()
    conn = MagicMock()
    with patch("custom_components.roommind.websocket_api.time.time", return_value=now):
        await websocket_override_set.__wrapped__(
            hass,
            conn,
            {
                "id": 1,
                "area_id": "bedroom",
                "override_type": "custom",
                "heat": 22,
                "cool": 23,
                "until_next_change": True,
            },
        )
    conn.send_error.assert_not_called()
    assert store.get_room("bedroom")["override_until"] == now + 3600
    await websocket_override_set.__wrapped__(
        hass, conn, {"id": 2, "area_id": "guest", "override_type": "boost", "until_next_change": True}
    )
    assert conn.send_error.call_args.args[1] == "invalid"


async def test_websocket_import_is_an_unassigned_draft(hass, scheduled_store):
    from custom_components.roommind.websocket_api import websocket_import_schedule

    conn = MagicMock()
    hass.states.get.return_value = MagicMock(attributes={"friendly_name": "Bedrooms"})
    with patch(
        "custom_components.roommind.utils.schedule_utils.read_schedule_blocks", new=AsyncMock(return_value=week())
    ):
        await websocket_import_schedule.__wrapped__(
            hass, conn, {"id": 1, "entity_id": "schedule.bedroom", "fallback_heat": 19, "fallback_cool": 19.5}
        )
    conn.send_error.assert_not_called()
    result = conn.send_result.call_args.args[1]["schedule"]
    assert result["name"] == "Bedrooms"
    assert result["id"] == ""
    assert result["area_ids"] == []
    assert scheduled_store.get_schedules() == {}
    with patch(
        "custom_components.roommind.utils.schedule_utils.read_schedule_blocks", new=AsyncMock(return_value=None)
    ):
        await websocket_import_schedule.__wrapped__(
            hass, conn, {"id": 2, "entity_id": "schedule.missing", "fallback_heat": 19, "fallback_cool": 19.5}
        )
    assert conn.send_error.call_args.args[1] == "invalid_schedule"


async def test_assignment_changes_invalidate_an_older_editor(scheduled_store):
    store = scheduled_store
    schedule = validate_schedule("Bedrooms", week())
    await store.async_save_schedule("a", schedule, ["bedroom"], 0)
    await store.async_save_room("guest", {"roommind_schedule_id": "a"})
    assert store.get_schedules()["a"]["revision"] == 2
    with pytest.raises(ValueError, match="another window"):
        await store.async_save_schedule("a", schedule, ["bedroom"], 1)
    await store.async_save_schedule("b", schedule, ["bedroom"], 0)
    assert store.get_schedules()["a"]["revision"] == 3
