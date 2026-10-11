"""Exercise real room planning, group arbitration and device command routing."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get

A = "climate.ac_living_room"
B = "climate.ac_master_bedroom"
T = "climate.tado_living_room"
BT = "climate.tado_master_bedroom"
GROUP = {
    "id": "toshiba",
    "members": [A, B],
    "shared_ac_control": True,
    "night_cooling_members": [B],
    "min_run_minutes": 5,
    "min_off_minutes": 5,
}


def setup(hass, entry, reverse=False, states=None, bedroom_enabled=True, outdoor=18):
    living = {
        **SAMPLE_ROOM,
        "area_id": "living",
        "temperature_sensor": "sensor.living_room_temp",
        "climate_mode": "heat_only",
        "comfort_heat": 21,
        "eco_heat": 21,
        "heat_source_orchestration": True,
        "devices": [
            {"entity_id": T, "type": "trv", "setpoint_mode": "direct", "setpoint_offset": 0.5},
            {"entity_id": A, "type": "ac", "setpoint_mode": "direct"},
        ],
    }
    bedroom = {
        **SAMPLE_ROOM,
        "area_id": "bedroom",
        "temperature_sensor": "sensor.bedroom_temp",
        "climate_mode": "auto",
        "comfort_heat": 19,
        "eco_heat": 19,
        "comfort_cool": 21,
        "eco_cool": 21,
        "climate_control_enabled": bedroom_enabled,
        "devices": [{"entity_id": BT, "type": "trv"}, {"entity_id": B, "type": "ac", "setpoint_mode": "direct"}],
    }
    pairs = [("living", living), ("bedroom", bedroom)]
    store = _make_store_mock(dict(reversed(pairs)) if reverse else dict(pairs), {"compressor_groups": [GROUP]})
    hass.data = {"roommind": {"store": store}}
    modes = {A: "off", B: "off", T: "heat", BT: "heat", **(states or {})}
    extra = {
        eid: (
            mode,
            {
                "hvac_modes": ["off", "heat", "cool", "fan_only"],
                "min_temp": 5 if eid in (T, BT) else 16,
                "max_temp": 25,
                "temperature": 21,
                "current_temperature": 21,
            },
        )
        for eid, mode in modes.items()
    }
    extra["sensor.bedroom_temp"] = ("23", {})
    hass.states.get = make_mock_states_get(temp="20.6", outdoor_temp=str(outdoor), extra=extra)
    hass.services.async_call = AsyncMock()
    return _create_coordinator(hass, entry), store


async def update(coordinator, hour=22, now=1000):
    with (
        patch("custom_components.roommind.managers.shared_ac_manager.time.time", return_value=now),
        patch(
            "custom_components.roommind.managers.shared_ac_manager.dt_util.now", return_value=datetime(2026, 7, 1, hour)
        ),
    ):
        return (await coordinator._async_update_data())["rooms"]


def calls(hass, eid):
    return [
        call.args[2]
        for call in hass.services.async_call.call_args_list
        if call.args[0] == "climate" and call.args[2].get("entity_id") == eid
    ]


@pytest.mark.parametrize("reverse", [False, True])
async def test_night_bedroom_cools_living_room_falls_back_to_gas(hass, mock_config_entry, reverse):
    coordinator, _ = setup(hass, mock_config_entry, reverse)
    live = await update(coordinator)
    assert any(c.get("hvac_mode") == "cool" for c in calls(hass, B))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
    assert any(c.get("hvac_mode") == "heat" for c in calls(hass, T))
    assert any(c.get("temperature") == 21.5 for c in calls(hass, T))
    assert any(c.get("hvac_mode") == "off" for c in calls(hass, BT))
    assert live["living"]["active_heat_sources"] == "primary"
    assert live["living"]["shared_ac_waiting_reason"] == "other_direction"
    assert live["bedroom"]["heating_blocked_by_cooling"]


async def test_daytime_heating_priority_parks_bedroom_ac(hass, mock_config_entry):
    coordinator, _ = setup(hass, mock_config_entry)
    live = await update(coordinator, hour=12)
    assert any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "cool" for c in calls(hass, B))
    assert live["bedroom"]["shared_ac_waiting_reason"] == "other_direction"


async def test_changeover_closes_old_mode_and_waits_for_confirmation(hass, mock_config_entry):
    coordinator, _ = setup(hass, mock_config_entry, states={A: "heat"})
    await update(coordinator)
    hass.services.async_call.reset_mock()
    live = await update(coordinator, now=1301)
    assert any(c.get("hvac_mode") == "off" for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "cool" for c in calls(hass, B))
    assert live["bedroom"]["shared_ac_waiting_reason"] == "changeover"
    assert any(c.get("hvac_mode") == "heat" for c in calls(hass, T))


async def test_disabled_bedroom_is_never_commanded(hass, mock_config_entry):
    coordinator, _ = setup(hass, mock_config_entry, states={B: "cool"}, bedroom_enabled=False)
    await update(coordinator)
    assert calls(hass, B) == [] and calls(hass, BT) == []
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
    assert any(c.get("hvac_mode") == "heat" for c in calls(hass, T))


async def test_unknown_auto_mode_keeps_radiators_usable_in_other_room(hass, mock_config_entry):
    coordinator, _ = setup(hass, mock_config_entry, states={B: "auto"})
    live = await update(coordinator)
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
    assert any(c.get("hvac_mode") == "heat" for c in calls(hass, T))
    assert live["living"]["shared_ac_waiting_reason"] == "unknown_status"
    assert live["bedroom"]["heating_blocked_by_cooling"]


async def test_global_disabled_sends_no_commands(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry, states={A: "heat", B: "cool"})
    store.get_settings.return_value["climate_control_active"] = False
    await update(coordinator)
    assert calls(hass, A) == [] and calls(hass, B) == [] and calls(hass, T) == [] and calls(hass, BT) == []


async def test_gas_only_source_preference_does_not_claim_heat_pump(hass, mock_config_entry):
    coordinator, _ = setup(hass, mock_config_entry, outdoor=-20)
    # The explicit cooling override bypasses the ordinary cold-outdoor cooling gate.
    store = hass.data["roommind"]["store"]
    store.get_rooms.return_value["bedroom"].update(
        override_type="custom", override_heat=19, override_cool=21, override_until=9999999999
    )
    await update(coordinator, hour=12)
    assert any(c.get("hvac_mode") == "cool" for c in calls(hass, B))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))


async def test_group_member_without_external_sensor_is_not_commanded(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    store.get_rooms.return_value["bedroom"]["temperature_sensor"] = ""
    live = await update(coordinator)
    assert calls(hass, B) == []
    assert live["bedroom"]["shared_ac_waiting_reason"] == "external_sensor_required"


async def test_roommind_owned_cooling_still_trains_thermal_model(hass, mock_config_entry):
    from unittest.mock import MagicMock

    coordinator, _ = setup(hass, mock_config_entry)
    coordinator._ekf_training.process = MagicMock()
    await update(coordinator)
    calls = coordinator._ekf_training.process.call_args_list
    assert any(call.kwargs["area_id"] == "bedroom" and call.kwargs["ekf_mode"] == "cooling" for call in calls)


async def test_open_window_stops_ac_even_during_shared_minimum_run(hass, mock_config_entry):
    from unittest.mock import MagicMock

    coordinator, store = setup(hass, mock_config_entry, states={A: "heat"})
    store.get_rooms.return_value["living"]["window_sensors"] = ["binary_sensor.window"]
    base = hass.states.get
    hass.states.get = lambda eid: MagicMock(state="on", attributes={}) if eid == "binary_sensor.window" else base(eid)
    await update(coordinator)
    assert any(c.get("hvac_mode") == "off" for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
