"""Exercise actual device routing at tariff cutoffs and boost targets."""

from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from .conftest import make_mock_states_get
from .test_shared_ac_control import BT, A, B, T, calls, setup, update


async def tariff_update(coordinator, hour=12, minute=0):
    now = datetime(2026, 7, 1, hour, minute, tzinfo=UTC).timestamp()
    with patch("custom_components.roommind.coordinator.time.time", return_value=now):
        return await update(coordinator, hour=hour, now=now)


def enable(store, boost=False):
    store.get_settings.return_value["compressor_groups"] = deepcopy(
        store.get_settings.return_value["compressor_groups"]
    )
    store.get_settings.return_value.update(
        ac_tariff_enabled=True,
        ac_morning_boost_enabled=boost,
        ac_morning_boost_rooms=["living"],
        control_mode="bangbang",
    )
    # No helper schedule in this test: constant independent-sensor comfort target.
    for room in store.get_rooms.return_value.values():
        room["schedules"] = []


async def test_peak_uses_gas_with_original_offset_and_cooling_remains_allowed(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store)
    live = await tariff_update(coordinator)
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
    assert any(c.get("temperature") == 21.5 for c in calls(hass, T))
    assert any(c.get("hvac_mode") == "cool" for c in calls(hass, B))
    assert any(c.get("hvac_mode") == "off" for c in calls(hass, BT))
    assert live["living"]["ac_heating_locked"] and live["living"]["ac_tariff_status"] == "peak"


async def test_peak_override_cannot_restart_ac(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry, states={A: "heat"})
    enable(store)
    store.get_rooms.return_value["living"].update(
        override_type="custom", override_until=9999999999, override_heat=24, override_cool=25
    )
    await tariff_update(coordinator)
    assert any(c.get("hvac_mode") == "off" for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
    assert any(c.get("temperature") == 24.5 for c in calls(hass, T))


async def test_final_cheap_minutes_use_morning_target_without_extra_device_bias(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"].update(climate_control_enabled=False)
    live = await tariff_update(coordinator, 4, 45)
    assert live["living"]["heat_target"] == 21
    assert live["living"]["ac_boost_target"] == 21
    assert any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
    assert not any(c.get("temperature", 0) > 21 for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, T))


@pytest.mark.parametrize("disabled", ["global", "room", "unowned"])
async def test_peak_never_commands_disabled_or_unowned_member(hass, mock_config_entry, disabled):
    coordinator, store = setup(hass, mock_config_entry, states={A: "heat"})
    enable(store)
    if disabled == "global":
        store.get_settings.return_value["climate_control_active"] = False
    elif disabled == "room":
        store.get_rooms.return_value["living"]["climate_control_enabled"] = False
    else:
        store.get_rooms.return_value["living"]["temperature_sensor"] = ""
    await tariff_update(coordinator)
    assert not calls(hass, A)


async def test_cutoff_overrides_shared_minimum_run(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    store.get_settings.return_value["compressor_groups"][0]["min_run_minutes"] = 30
    await tariff_update(coordinator, 4, 59)
    hass.services.async_call.reset_mock()
    hass.states.get = make_mock_states_get(
        temp="20.6",
        outdoor_temp="18",
        extra={
            A: ("heat", {"hvac_modes": ["off", "heat", "cool"], "temperature": 24, "min_temp": 16, "max_temp": 30}),
            B: ("off", {}),
        },
    )
    live = await tariff_update(coordinator, 5)
    assert live["living"]["ac_heating_locked"]
    assert any(c.get("hvac_mode") == "off" for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))


async def test_boost_reaching_independent_target_stops_despite_minimum_run(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    store.get_settings.return_value["compressor_groups"][0]["min_run_minutes"] = 30
    await tariff_update(coordinator, 4, 45)
    hass.services.async_call.reset_mock()
    hass.states.get = make_mock_states_get(
        temp="21.0",
        outdoor_temp="18",
        extra={
            A: ("heat", {"hvac_modes": ["off", "heat", "cool"], "temperature": 24, "min_temp": 16, "max_temp": 30}),
            B: ("off", {}),
        },
    )
    await tariff_update(coordinator, 4, 46)
    assert any(c.get("hvac_mode") == "off" for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))


async def test_peak_ac_idle_setback_cannot_restart_heat(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store)
    store.get_rooms.return_value["living"]["comfort_heat"] = 19
    store.get_rooms.return_value["living"]["eco_heat"] = 19
    store.get_rooms.return_value["living"]["devices"][1].update(idle_action="setback", idle_setback=1)
    await tariff_update(coordinator)
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))


async def test_peak_ac_only_room_stays_idle(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store)
    store.get_rooms.return_value["living"]["devices"] = [{"entity_id": A, "type": "ac"}]
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    live = await tariff_update(coordinator)
    assert live["living"]["mode"] == "idle"
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))


async def test_boost_at_target_does_not_restart_idle_setback(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    store.get_rooms.return_value["living"]["devices"][1].update(idle_action="setback", idle_setback=1)
    hass.states.get = make_mock_states_get(
        temp="21.0",
        outdoor_temp="18",
        extra={
            A: ("off", {"hvac_modes": ["off", "heat", "cool"], "temperature": 24, "min_temp": 16, "max_temp": 30}),
            B: ("off", {}),
        },
    )
    await tariff_update(coordinator, 4, 46)
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))


async def test_legacy_boost_offset_is_ignored(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_settings.return_value["ac_morning_boost_offset"] = 5
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    await tariff_update(coordinator, 4, 45)
    assert not any(c.get("temperature", 0) > 21 for c in calls(hass, A))
    assert not any(c.get("temperature", 0) > 21 for c in calls(hass, A))


async def test_boost_stops_below_target_and_stays_off_after_reload(hass, mock_config_entry):
    from .conftest import _create_coordinator

    coordinator, store = setup(hass, mock_config_entry, states={A: "heat"})
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    store.get_rooms.return_value["living"]["devices"][0].update(idle_action="setback")
    hass.states.get = make_mock_states_get(
        temp="20.8",
        outdoor_temp="18",
        extra={A: ("heat", {"hvac_modes": ["off", "heat", "cool"], "temperature": 24}), B: ("off", {})},
    )
    await tariff_update(coordinator, 4, 45)
    assert any(c.get("hvac_mode") == "off" for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, T))
    persisted = next(
        call.args[0]["ac_tariff_boost_state"]
        for call in store.async_save_settings.call_args_list
        if "ac_tariff_boost_state" in call.args[0]
    )
    store.get_settings.return_value["ac_tariff_boost_state"] = persisted
    coordinator = _create_coordinator(hass, mock_config_entry)
    hass.services.async_call.reset_mock()
    hass.states.get = make_mock_states_get(
        temp="20.7",
        outdoor_temp="18",
        extra={A: ("off", {"hvac_modes": ["off", "heat", "cool"], "temperature": 21}), B: ("off", {})},
    )
    await tariff_update(coordinator, 4, 46)
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))


async def test_constant_equal_targets_do_not_cool_at_cutoff(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    store.get_rooms.return_value["living"].update(climate_mode="auto", comfort_cool=21, eco_cool=21)
    await tariff_update(coordinator, 4, 45)
    hass.services.async_call.reset_mock()
    hass.states.get = make_mock_states_get(
        temp="21.2",
        outdoor_temp="18",
        extra={A: ("off", {"hvac_modes": ["off", "heat", "cool"], "temperature": 21}), B: ("off", {})},
    )
    live = await tariff_update(coordinator, 5, 1)
    assert live["living"]["cool_target"] == 21.5
    assert not any(c.get("hvac_mode") == "cool" for c in calls(hass, A))
    assert live["living"]["ac_tariff_status"] == "warmth_hold"


async def test_cooling_override_cancels_handover_hold(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    store.get_rooms.return_value["living"].update(climate_mode="auto", comfort_cool=21, eco_cool=21)
    await tariff_update(coordinator, 4, 45)
    hass.services.async_call.reset_mock()
    store.get_rooms.return_value["living"].update(override_heat=18, override_cool=19, override_until=9999999999)
    live = await tariff_update(coordinator, 5, 1)
    assert live["living"]["cool_target"] == 19
    # An explicit override cancels the hold; shared changeover time still applies.
    await tariff_update(coordinator, 5, 7)
    assert any(c.get("hvac_mode") == "cool" for c in calls(hass, A))


async def test_mould_prevention_does_not_inflate_morning_preparation_target(hass, mock_config_entry):
    from unittest.mock import AsyncMock

    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    coordinator._evaluate_mold_risk = AsyncMock(return_value=("warning", 75, 15.0, True, 3.0))
    live = await tariff_update(coordinator, 4, 45)
    assert live["living"]["heat_target"] == 21
    assert live["living"]["ac_boost_target"] == 21
    assert not any(c.get("temperature", 0) > 21 for c in calls(hass, A))


async def test_handover_still_allows_automatic_cooling_when_genuinely_hot(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    store.get_rooms.return_value["living"].update(climate_mode="auto", comfort_cool=21, eco_cool=21)
    await tariff_update(coordinator, 4, 45)
    hass.services.async_call.reset_mock()
    hass.states.get = make_mock_states_get(
        temp="23",
        outdoor_temp="18",
        extra={A: ("off", {"hvac_modes": ["off", "heat", "cool"], "temperature": 21}), B: ("off", {})},
    )
    await tariff_update(coordinator, 5, 1)
    await tariff_update(coordinator, 5, 7)
    assert any(c.get("hvac_mode") == "cool" for c in calls(hass, A))


async def test_sensor_dropout_pauses_heating_without_discarding_cooling_hold(hass, mock_config_entry):
    coordinator, store = setup(hass, mock_config_entry)
    enable(store, boost=True)
    store.get_rooms.return_value["bedroom"]["climate_control_enabled"] = False
    await tariff_update(coordinator, 4, 45)
    hass.services.async_call.reset_mock()
    hass.states.get = make_mock_states_get(
        temp="unavailable",
        outdoor_temp="18",
        extra={A: ("heat", {"hvac_modes": ["off", "heat", "cool"], "temperature": 21}), B: ("off", {})},
    )
    live = await tariff_update(coordinator, 4, 46)
    assert live["living"]["cool_target"] == 24
    assert coordinator._heating_tariff.state["living"]["heating_paused"]
    assert any(c.get("hvac_mode") == "off" for c in calls(hass, A))
    assert not any(c.get("hvac_mode") == "heat" for c in calls(hass, A))
