"""Upgrade a household fork configuration without blocking current editors."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.roommind.const import DOMAIN, VERSION
from custom_components.roommind.websocket_api import websocket_save_room, websocket_save_settings


def old_fork_data():
    """Representative values from the cooling-interlock and Mods releases."""
    return {
        "rooms": {
            "bedroom": {
                "area_id": "bedroom",
                "thermostats": [],
                "acs": ["climate.bedroom_ac"],
                "temperature_sensor": "sensor.bedroom_temperature",
                "devices": [
                    {
                        "entity_id": "climate.bedroom_ac",
                        "type": "ac",
                        "role": "auto",
                        "idle_action": "setback",
                        "setpoint_mode": "direct",
                        "setpoint_offset": 0.5,
                        "energy_sensor": "sensor.bedroom_ac_energy",
                    },
                ],
                "schedules": [{"entity_id": "schedule.bedrooms"}],
                "preheat_enabled": True,
                "preheat_max_minutes": 60,
                "roommind_schedule_id": "bedrooms",
                "cooling_interlock_entities": ["climate.bedroom_ac"],
                "cooling_interlock_delay": 300,
                "cooling_interlock_deadband": 0.3,
                "ac_off_peak_allow_radiators": True,
                "dehumidifier_power_sensor": "sensor.dehumidifier_power",
                "dehumidifier_switch": None,
                "dehumidifier_entity": "humidifier.dehumidifier",
                "heat_source_assist_enabled": True,
                "heat_source_assist_delta": 1.0,
            },
        },
        "settings": {
            "price_entity": "switch.cheap_electricity",
            "boost_applied_at": {"bedroom": 10},
            "valve_last_actuation": {"climate.trv": 123},
            "coil_dry_state": {"climate.bedroom_ac": {"phase": "blow"}},
            "heat_pump_power_sensor": "sensor.heat_pump_power",
            "heat_pump_active_watts": 100,
            "ac_tariff_enabled": True,
            "ac_off_peak_start": "00:00",
            "ac_off_peak_end": "05:00",
            "ac_morning_boost_enabled": True,
            "ac_morning_boost_minutes": 30,
            "ac_morning_boost_offset": 2,
            "ac_morning_boost_stop_margin": 0.2,
            "ac_morning_boost_rooms": ["bedroom"],
            "ac_tariff_boost_state": {"bedroom": {"heating_paused": True}},
            "cooling_interlock_state": {"active": ["bedroom"]},
            "shared_ac_state": {"climate.bedroom_ac": "heat"},
            "compressor_groups": [
                {
                    "id": "toshiba",
                    "name": "Toshiba",
                    "members": ["climate.bedroom_ac"],
                    "min_run_minutes": 5,
                    "min_off_minutes": 5,
                    "shared_ac_control": True,
                    "heating_idle_mode": "minimum_heat",
                    "night_cooling_members": ["climate.bedroom_ac"],
                },
            ],
        },
        "thermal_data": {"bedroom": {"n_observations": 100}},
        "reusable_schedules": {"bedrooms": {"name": "Bedrooms", "days": {}}},
    }


@pytest.mark.asyncio
async def test_old_fork_settings_are_backed_up_and_removed_before_editing(store, hass):
    original = old_fork_data()
    store._store.async_load.return_value = copy.deepcopy(original)
    store._legacy_fork_backup = AsyncMock()
    store._legacy_fork_backup.async_load.return_value = None

    await store.async_load()

    store._legacy_fork_backup.async_save.assert_awaited_once_with(original)
    saved = store._store.async_save.call_args.args[0]
    assert set(saved) == {"rooms", "settings", "thermal_data"}
    assert saved["thermal_data"] == original["thermal_data"]
    room = store.get_room("bedroom")
    # The whole current room configuration must pass the same schema as the editor.
    websocket_save_room._ws_schema({"id": 1, "type": "roommind/rooms/save", **room})
    settings = store.get_settings()
    assert set(settings) == {
        "price_entity",
        "boost_applied_at",
        "valve_last_actuation",
        "coil_dry_state",
        "compressor_groups",
    }
    websocket_save_settings._ws_schema(
        {"id": 2, "type": "roommind/settings/save", "compressor_groups": settings["compressor_groups"]}
    )
    assert room["heat_source_assist_enabled"] is True
    assert room["heat_source_assist_delta"] == 1.0
    assert room["dehumidifier_entity"] == "humidifier.dehumidifier"
    assert room["schedules"] == original["rooms"]["bedroom"]["schedules"]
    assert room["devices"][0]["idle_action"] == "setback"
    assert room["devices"][0]["setpoint_offset"] == 0.5

    # A second boot neither rewrites the data nor overwrites the recovery snapshot.
    store._store.async_load.return_value = copy.deepcopy(saved)
    store._store.async_save.reset_mock()
    await store.async_load()
    store._store.async_save.assert_not_awaited()
    store._legacy_fork_backup.async_save.assert_awaited_once()

    # Go through schema validation AND the save handlers after the upgrade.
    hass.data[DOMAIN] = {"store": store}
    connection = MagicMock()
    for field, value in (
        ("idle_action", "fan_only"),
        ("setback_auto_off", True),
        ("setpoint_mode", "proportional"),
        ("setpoint_offset", 1.0),
        ("coil_dry", "on"),
        ("coil_dry_minutes", 25),
        ("coil_dry_mode", "dry"),
        ("coil_dry_fan_mode", "__keep__"),
    ):
        devices = store.get_room("bedroom")["devices"]
        devices[0][field] = value
        message = websocket_save_room._ws_schema(
            {"id": 3, "type": "roommind/rooms/save", "area_id": "bedroom", "devices": devices}
        )
        await websocket_save_room.__wrapped__(hass, connection, message)
        assert store.get_room("bedroom")["devices"][0][field] == value
    groups = store.get_settings()["compressor_groups"]
    groups[0]["min_run_minutes"] = 10
    message = websocket_save_settings._ws_schema(
        {"id": 4, "type": "roommind/settings/save", "compressor_groups": groups}
    )
    await websocket_save_settings.__wrapped__.__wrapped__(hass, connection, message)
    assert store.get_settings()["compressor_groups"][0]["min_run_minutes"] == 10
    connection.send_error.assert_not_called()
    assert connection.send_result.call_count == 9


@pytest.mark.asyncio
async def test_failed_backup_does_not_overwrite_main_storage(store):
    store._store.async_load.return_value = old_fork_data()
    store._legacy_fork_backup = AsyncMock()
    store._legacy_fork_backup.async_load.return_value = None
    store._legacy_fork_backup.async_save.side_effect = OSError("Storage unavailable")
    with pytest.raises(OSError, match="Storage unavailable"):
        await store.async_load()
    store._store.async_save.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_paths_cannot_reintroduce_retired_fork_fields(store):
    await store.async_load()
    old = old_fork_data()
    await store.async_save_room("bedroom", old["rooms"]["bedroom"])
    await store.async_update_room("bedroom", {"preheat_max_minutes": None})
    await store.async_save_settings(old["settings"])
    saved = store._store.async_save.call_args.args[0]
    assert "preheat_max_minutes" not in saved["rooms"]["bedroom"]
    assert "energy_sensor" not in saved["rooms"]["bedroom"]["devices"][0]
    assert "ac_tariff_enabled" not in saved["settings"]
    assert "shared_ac_control" not in saved["settings"]["compressor_groups"][0]
    assert saved["settings"]["coil_dry_state"] == old["settings"]["coil_dry_state"]


def test_frontend_cache_version_matches_the_personal_release():
    """Personal updates must request new JS, rather than the upstream release's cached UI."""
    manifest = Path(__file__).parents[1] / "custom_components/roommind/manifest.json"
    assert VERSION == json.loads(manifest.read_text())["version"]
