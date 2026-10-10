"""Regression tests: external cooling must override every radiator heat path."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

AC = "climate.external_toshiba"
TRV = "climate.living_room"


def setup(hass, mock_config_entry, *, settings=None, monitored=True, temperature="18.0", idle_action="off"):
    room = {
        **SAMPLE_ROOM,
        "cooling_interlock_entities": [AC] if monitored else [],
        "devices": [{"entity_id": TRV, "type": "trv", "idle_action": idle_action}],
    }
    store = _make_store_mock({room["area_id"]: room}, settings)
    hass.data = {"roommind": {"store": store}}
    hass.services.async_call = AsyncMock()
    hass.states.get = make_mock_states_get(
        temp=temperature,
        extra={
            TRV: ("heat", {"hvac_modes": ["off", "heat"], "min_temp": 5, "max_temp": 30}),
            AC: ("cool", {"hvac_modes": ["off", "heat", "cool"]}),
        },
    )
    coordinator = _create_coordinator(hass, mock_config_entry)
    coordinator._ekf_training.process = MagicMock()
    return coordinator, room


def climate_calls(hass, entity_id):
    return [
        (call.args[1], call.args[2])
        for call in hass.services.async_call.call_args_list
        if call.args[0] == "climate" and call.args[2].get("entity_id") == entity_id
    ]


@pytest.mark.parametrize("idle_action", ["off", "setback", "low"])
async def test_external_cooling_closes_radiator_without_touching_ac(hass, mock_config_entry, idle_action):
    coordinator, room = setup(hass, mock_config_entry, idle_action=idle_action)
    data = await coordinator._async_update_data()
    live = data["rooms"][room["area_id"]]
    assert live["heating_blocked_by_cooling"]
    assert live["cooling_interlock_reason"] == "cooling"
    assert live["commanded_mode"] == "idle"
    assert ("set_hvac_mode", {"entity_id": TRV, "hvac_mode": "off"}) in climate_calls(hass, TRV)
    assert not any(d.get("hvac_mode") == "heat" for _, d in climate_calls(hass, TRV))
    assert climate_calls(hass, AC) == []
    coordinator._ekf_training.process.assert_not_called()
    assert coordinator._model_manager.get_estimator(room["area_id"])._x[0] == 18.0


async def test_off_by_default_keeps_existing_heating(hass, mock_config_entry):
    coordinator, room = setup(hass, mock_config_entry, monitored=False)
    data = await coordinator._async_update_data()
    assert not data["rooms"][room["area_id"]]["heating_blocked_by_cooling"]
    assert any(d.get("hvac_mode") == "heat" for _, d in climate_calls(hass, TRV))


async def test_startup_missing_sensor_still_closes_heat_against_cooling(hass, mock_config_entry):
    coordinator, _ = setup(hass, mock_config_entry, temperature=None)
    await coordinator._async_update_data()
    assert ("set_hvac_mode", {"entity_id": TRV, "hvac_mode": "off"}) in climate_calls(hass, TRV)


@pytest.mark.parametrize("settings", [{"climate_control_active": False}, {}])
async def test_disabled_control_is_respected(hass, mock_config_entry, settings):
    coordinator, room = setup(hass, mock_config_entry, settings=settings)
    room["climate_control_enabled"] = False
    await coordinator._async_update_data()
    assert climate_calls(hass, TRV) == []


async def test_valve_protection_cannot_reopen_blocked_radiator(hass, mock_config_entry):
    coordinator, room = setup(hass, mock_config_entry, settings={"valve_protection_enabled": True})
    coordinator._valve_manager._cycling[TRV] = 1e20
    coordinator._valve_manager.should_run_cycle_check = MagicMock(return_value=True)
    await coordinator._async_update_data()
    assert TRV not in coordinator._valve_manager.cycling_eids
    assert not any(d.get("hvac_mode") == "heat" for _, d in climate_calls(hass, TRV))
    assert coordinator.rooms[room["area_id"]]["heating_blocked_by_cooling"]


async def test_another_room_can_still_heat(hass, mock_config_entry):
    coordinator, room = setup(hass, mock_config_entry)
    other = {**SAMPLE_ROOM, "area_id": "other", "devices": [{"entity_id": "climate.other", "type": "trv"}]}
    hass.data["roommind"]["store"].get_rooms.return_value["other"] = other
    base = hass.states.get
    hass.states.get = lambda eid: (
        make_mock_states_get(extra={"climate.other": ("heat", {"hvac_modes": ["off", "heat"]})})(eid)
        if eid == "climate.other"
        else base(eid)
    )
    data = await coordinator._async_update_data()
    assert data["rooms"][room["area_id"]]["commanded_mode"] == "idle"
    assert data["rooms"]["other"]["commanded_mode"] == "heating"
    assert any(d.get("hvac_mode") == "heat" for _, d in climate_calls(hass, "climate.other"))


async def test_store_round_trip_and_websocket_status(hass):
    from custom_components.roommind.store import RoomMindStore
    from custom_components.roommind.websocket_api import websocket_list_rooms

    store = RoomMindStore(hass)
    store._store = AsyncMock()
    values = {"cooling_interlock_entities": [AC], "cooling_interlock_delay": 120, "cooling_interlock_deadband": 0.2}
    room = await store.async_save_room("bedroom", values)
    assert all(room[key] == value for key, value in values.items())
    await store.async_save_room("bedroom", {"display_name": "Bedroom"})
    assert store.get_room("bedroom")["cooling_interlock_entities"] == [AC]
    coordinator = MagicMock()
    coordinator.rooms = {"bedroom": {"heating_blocked_by_cooling": True, "cooling_interlock_reason": "cooling"}}
    hass.data = {"roommind": {"store": store, "coordinator": coordinator}}
    connection = MagicMock()
    await websocket_list_rooms.__wrapped__(hass, connection, {"id": 1})
    live = connection.send_result.call_args.args[1]["rooms"]["bedroom"]["live"]
    assert live["heating_blocked_by_cooling"]
    assert live["cooling_interlock_reason"] == "cooling"
