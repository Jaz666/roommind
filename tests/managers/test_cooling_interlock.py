"""Tests for selected-mode cooling protection and recovery hysteresis."""

from unittest.mock import MagicMock

import pytest
from homeassistant.core import State

from custom_components.roommind.managers.cooling_interlock import CoolingInterlock

ROOM = {"area_id": "bedroom", "cooling_interlock_entities": ["climate.ac"]}


@pytest.fixture
def guard(hass):
    hass.states.get = MagicMock(return_value=State("climate.ac", "off"))
    return CoolingInterlock(hass)


def evaluate(guard, room=None, **kwargs):
    return guard.evaluate(
        room or ROOM,
        commanded_cooling=kwargs.get("commanded_cooling", False),
        current_temp=kwargs.get("current_temp", 18.0),
        heat_target=kwargs.get("heat_target", 19.0),
    )


@pytest.mark.parametrize("mode", ["cool", "dry"])
@pytest.mark.parametrize("action", [None, "idle", "cooling"])
def test_selected_cooling_blocks_even_when_compressor_idle(guard, hass, mode, action):
    hass.states.get.return_value = State("climate.ac", mode, {"hvac_action": action})
    assert evaluate(guard) == "cooling"


def test_observed_cooling_blocks_auto_mode(guard, hass):
    hass.states.get.return_value = State("climate.ac", "auto", {"hvac_action": "cooling"})
    assert evaluate(guard) == "cooling"


@pytest.mark.parametrize("mode", ["auto", "heat_cool", "unknown", "unavailable", None])
def test_uncertain_status_blocks_heat(guard, hass, mode):
    hass.states.get.return_value = State("climate.ac", mode) if mode else None
    assert evaluate(guard) == "cooling_status_unknown"


@pytest.mark.parametrize("mode", ["heat", "off", "fan_only"])
def test_known_non_cooling_does_not_block(guard, hass, mode):
    hass.states.get.return_value = State("climate.ac", mode)
    assert evaluate(guard) is None


def test_commanded_cooling_blocks_before_device_feedback(guard):
    assert evaluate(guard, commanded_cooling=True) == "cooling"


def test_recovery_requires_elapsed_delay_and_temperature_margin(guard, hass, monkeypatch):
    now = [0.0]
    monkeypatch.setattr("custom_components.roommind.managers.cooling_interlock.time.time", lambda: now[0])
    hass.states.get.return_value = State("climate.ac", "cool")
    assert evaluate(guard) == "cooling"
    now[0] = 100.0
    hass.states.get.return_value = State("climate.ac", "off")
    assert evaluate(guard) == "recovery"
    now[0] = 399.0
    assert evaluate(guard) == "recovery"
    now[0] = 400.0
    assert evaluate(guard, current_temp=18.7) == "recovery"
    assert evaluate(guard, current_temp=18.6) is None


@pytest.mark.parametrize("missing", ["current_temp", "heat_target"])
def test_missing_temperature_or_target_cannot_release_recovery(guard, hass, missing):
    assert evaluate(guard, commanded_cooling=True) == "cooling"
    assert evaluate(guard, {**ROOM, "cooling_interlock_delay": 0}, **{missing: None}) == "recovery"


def test_unknown_status_restarts_recovery_after_reconnecting(guard, hass, monkeypatch):
    now = [0.0]
    monkeypatch.setattr("custom_components.roommind.managers.cooling_interlock.time.time", lambda: now[0])
    assert evaluate(guard, commanded_cooling=True) == "cooling"
    assert evaluate(guard) == "recovery"
    now[0] = 290.0
    hass.states.get.return_value = None
    assert evaluate(guard) == "cooling_status_unknown"
    now[0] = 400.0
    hass.states.get.return_value = State("climate.ac", "off")
    assert evaluate(guard) == "recovery"
    now[0] = 699.0
    assert evaluate(guard) == "recovery"
    now[0] = 700.0
    assert evaluate(guard) is None


def test_disabling_clears_the_latch(guard):
    assert evaluate(guard, commanded_cooling=True) == "cooling"
    assert evaluate(guard, {"area_id": "bedroom"}, commanded_cooling=True) is None
    assert evaluate(guard) is None


def test_multiple_monitors_any_cooling_blocks(guard, hass):
    hass.states.get.side_effect = lambda eid: State(eid, "cool" if eid.endswith("2") else "off")
    assert evaluate(guard, {**ROOM, "cooling_interlock_entities": ["climate.ac", "climate.ac2"]}) == "cooling"


def test_room_latches_are_independent(guard):
    assert evaluate(guard, commanded_cooling=True) == "cooling"
    assert evaluate(guard, {**ROOM, "area_id": "other"}) is None
    assert evaluate(guard) == "recovery"


def test_recovery_survives_restart(guard, hass, monkeypatch):
    now = [100.0]
    monkeypatch.setattr("custom_components.roommind.managers.cooling_interlock.time.time", lambda: now[0])
    assert evaluate(guard, commanded_cooling=True) == "cooling"
    assert evaluate(guard) == "recovery"
    saved = guard.get_state()
    restored = CoolingInterlock(hass)
    restored.load_state(saved)
    now[0] = 399.0
    assert evaluate(restored) == "recovery"
    now[0] = 400.0
    assert evaluate(restored) is None


def test_active_cooling_latch_survives_restart(guard, hass):
    assert evaluate(guard, commanded_cooling=True) == "cooling"
    restored = CoolingInterlock(hass)
    restored.load_state(guard.get_state())
    assert evaluate(restored) == "recovery"


def test_paused_temperature_sync_preserves_thermal_parameters():
    from copy import deepcopy

    from custom_components.roommind.control.thermal_model import ThermalEKF

    model = ThermalEKF()
    model.update(21.0, 5.0, "idle", 3.0)
    model.update(20.9, 5.0, "idle", 3.0)
    params = model._x[1:]
    covariance = deepcopy(model._P)
    count = model._n_updates
    model.sync_temperature(18.0)
    assert model._x[0] == 18.0
    assert model._x[1:] == params
    assert model._P == covariance
    assert model._n_updates == count
