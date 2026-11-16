"""Reusable schedules drive current targets and analytics without HA helpers."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.roommind.services.analytics_service import _compute_target_forecast
from custom_components.roommind.utils.reusable_schedule import validate_schedule
from tests.utils.test_reusable_schedule import week

from .conftest import SAMPLE_ROOM, _create_coordinator, _make_store_mock, make_mock_states_get


@pytest.mark.parametrize("hour,expected", [(6, 19), (7, 20), (22, 19), (23, 19)])
async def test_current_targets_use_linked_schedule(hass, mock_config_entry, hour, expected):
    room = {**SAMPLE_ROOM, "roommind_schedule_id": "bedrooms"}
    store = _make_store_mock({room["area_id"]: room})
    store.get_schedules.return_value = {"bedrooms": validate_schedule("Bedrooms", week())}
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get(schedule_state="off"))
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    now = datetime(2026, 7, 6, hour, tzinfo=ZoneInfo("UTC")).timestamp()
    with patch("custom_components.roommind.coordinator.time.time", return_value=now):
        data = await coordinator._async_update_data()
    live = data["rooms"][room["area_id"]]
    assert live["heat_target"] == expected
    assert live["cool_target"] == expected + 0.5
    assert not any(call.args[:2] == ("schedule", "get_schedule") for call in hass.services.async_call.call_args_list)


@pytest.mark.parametrize(
    "room_changes,settings,expected",
    [
        ({"override_heat": 22, "override_cool": 23, "override_until": None}, {}, 22),
        ({}, {"vacation_until": 9999999999, "vacation_temp": 16}, 16),
        ({"roommind_schedule_id": "missing"}, {}, 21),
    ],
)
async def test_priority_and_missing_reference(hass, mock_config_entry, room_changes, settings, expected):
    room = {**SAMPLE_ROOM, "roommind_schedule_id": "bedrooms", **room_changes}
    store = _make_store_mock({room["area_id"]: room}, settings)
    store.get_schedules.return_value = {"bedrooms": validate_schedule("Bedrooms", week())}
    hass.data = {"roommind": {"store": store}}
    hass.states.get = MagicMock(side_effect=make_mock_states_get())
    hass.services.async_call = AsyncMock()
    coordinator = _create_coordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()
    assert data["rooms"][room["area_id"]]["heat_target"] == expected


async def test_analytics_forecast_uses_same_schedule_and_units(hass):
    room = {**SAMPLE_ROOM, "roommind_schedule_id": "bedrooms"}
    store = _make_store_mock({room["area_id"]: room})
    store.get_schedules.return_value = {"bedrooms": validate_schedule("Bedrooms", week())}
    hass.data = {"roommind": {"store": store}}
    hass.config.units.temperature_unit = "°F"
    now = datetime(2026, 7, 6, 21, 55, tzinfo=ZoneInfo("UTC")).timestamp()
    with patch("custom_components.roommind.services.analytics_service.time.time", return_value=now):
        forecast = await _compute_target_forecast(hass, room, {}, hours=0.25)
    assert forecast[0]["heat_target"] == 20
    assert forecast[1]["heat_target"] == 19
    assert forecast[1]["cool_target"] == 19.5
