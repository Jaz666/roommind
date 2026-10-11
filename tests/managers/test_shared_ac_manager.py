"""Shared direction decisions use all demands, local time and reported states."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from custom_components.roommind.managers.shared_ac_manager import SharedACManager

A = "climate.lounge"
B = "climate.bedroom"
GROUP = {
    "id": "toshiba",
    "members": [A, B],
    "shared_ac_control": True,
    "night_cooling_members": [B],
    "min_run_minutes": 5,
    "min_off_minutes": 5,
}


def prepare(eid, mode, commandable=True):
    return {
        "prepared": True,
        "room": {"devices": [{"entity_id": eid, "type": "ac"}]},
        "mode": mode,
        "commandable": commandable,
    }


def manager(states):
    hass = MagicMock()
    hass.states.get.side_effect = lambda eid: MagicMock(state=states[eid]) if eid in states else None
    return SharedACManager(hass)


def resolve(mgr, demands, now=1000, hour=22, groups=None):
    with (
        patch("custom_components.roommind.managers.shared_ac_manager.time.time", return_value=now),
        patch(
            "custom_components.roommind.managers.shared_ac_manager.dt_util.now", return_value=datetime(2026, 7, 1, hour)
        ),
    ):
        mgr.resolve(groups or [GROUP], demands)
    return mgr.decisions[A]


@pytest.mark.parametrize("hour,expected", [(21, "heat"), (22, "cool"), (0, "cool"), (6, "cool"), (7, "heat")])
@pytest.mark.parametrize("reverse", [False, True])
def test_local_bedtime_priority_independent_of_room_order(hour, expected, reverse):
    mgr = manager({A: "off", B: "off"})
    demands = [prepare(A, "heating"), prepare(B, "cooling")]
    action = resolve(mgr, list(reversed(demands)) if reverse else demands, hour=hour).action
    assert action == expected
    assert mgr.blocked(A, "heating") == (expected == "cool")
    assert mgr.blocked(B, "cooling") == (expected == "heat")


def test_unselected_bedroom_does_not_take_night_priority():
    mgr = manager({A: "off", B: "off"})
    assert (
        resolve(
            mgr, [prepare(A, "heating"), prepare(B, "cooling")], groups=[{**GROUP, "night_cooling_members": []}]
        ).action
        == "heat"
    )


@pytest.mark.parametrize("mode,action", [("heating", "heat"), ("cooling", "cool"), ("idle", "idle")])
def test_matching_requests(mode, action):
    mgr = manager({A: "off", B: "off"})
    assert resolve(mgr, [prepare(A, mode), prepare(B, mode)]).action == action


def test_changeover_waits_for_reported_off_then_minimum_off_and_survives_reload():
    states = {A: "heat", B: "off"}
    mgr = manager(states)
    demands = [prepare(A, "heating"), prepare(B, "cooling")]
    first = resolve(mgr, demands)
    assert first.action == "heat" and first.reason == "minimum_run"
    assert first.hold == {A}
    stop = resolve(mgr, demands, now=1301)
    assert stop.stop == {A} and stop.action == "idle"
    # Even an accepted off command is not a reported-off state.
    assert resolve(mgr, demands, now=1700).action == "idle"
    states[A] = "off"
    wait = resolve(mgr, demands, now=1701)
    assert wait.reason == "minimum_off"
    restored = manager(states)
    restored.state = mgr.state
    assert resolve(restored, demands, now=1999).action == "idle"
    assert resolve(restored, demands, now=2001).action == "cool"


def test_delayed_start_report_cannot_reverse_direction():
    mgr = manager({A: "off", B: "off"})
    assert resolve(mgr, [prepare(A, "heating")], hour=12).action == "heat"
    switched = resolve(mgr, [prepare(A, "idle"), prepare(B, "cooling")], now=1030)
    assert switched.action == "idle" and switched.stop == {A, B}
    assert resolve(mgr, [prepare(B, "cooling")], now=1091).reason == "minimum_off"
    assert resolve(mgr, [prepare(B, "cooling")], now=1391).action == "cool"


@pytest.mark.parametrize("bad", ["auto", "heat_cool", "unknown", "unavailable", None])
def test_unknown_member_prevents_new_direction(bad):
    states = {A: "heat"}
    if bad is not None:
        states[B] = bad
    mgr = manager(states)
    decision = resolve(mgr, [prepare(A, "heating"), prepare(B, "cooling")])
    assert decision.action == "idle" and decision.reason == "unknown_status"
    assert decision.stop == {A}


def test_disabled_room_is_never_stopped_or_taken_over():
    mgr = manager({A: "heat", B: "cool"})
    decision = resolve(mgr, [prepare(A, "heating"), prepare(B, "cooling", False)])
    assert decision.reason == "conflicting_modes" and decision.stop == {A}
    assert B not in decision.owned


def test_external_unit_determines_direction_without_ownership():
    mgr = manager({A: "off", B: "cool"})
    decision = resolve(mgr, [prepare(A, "heating")])
    assert decision.action == "cool" and decision.reason == "external_control"
    assert not decision.stop and B not in decision.owned


def test_missing_preparation_and_removed_groups_clear_decisions():
    mgr = manager({A: "off", B: "off"})
    resolve(mgr, [{"mode": "idle"}, prepare(A, "heating")])
    mgr.resolve([], [])
    assert mgr.state == {} and mgr.decisions == {}
    assert not mgr.blocked(A, "heating")


def test_changed_members_preserve_outdoor_unit_timers():
    mgr = manager({A: "off", B: "off"})
    mgr.state = {"toshiba": {"members": [A], "direction": "heat", "on_since": 100}}
    assert resolve(mgr, [prepare(B, "cooling")]).reason == "minimum_off"


def test_idle_request_stops_after_minimum_run():
    states = {A: "cool", B: "off"}
    mgr = manager(states)
    assert resolve(mgr, [prepare(A, "idle")]).hold == {A}
    assert resolve(mgr, [prepare(A, "idle")], now=1301).stop == {A}
    states[A] = "off"
    assert resolve(mgr, [prepare(A, "idle")], now=1302).reason == "minimum_off"
    assert resolve(mgr, [prepare(A, "idle")], now=1603).action == "idle"


def test_auto_only_unit_cannot_be_started_in_shared_explicit_mode():
    mgr = manager({A: "off", B: "off"})
    unsupported = MagicMock(state="off", attributes={"hvac_modes": ["off", "auto"]})
    base = mgr.hass.states.get.side_effect
    mgr.hass.states.get.side_effect = lambda eid: unsupported if eid == B else base(eid)
    assert resolve(mgr, [prepare(A, "heating"), prepare(B, "cooling")]).reason == "unknown_status"


def test_window_or_force_off_bypasses_minimum_run_hold():
    mgr = manager({A: "heat", B: "off"})
    item = prepare(A, "idle")
    item["stop_immediately"] = True
    decision = resolve(mgr, [item, prepare(B, "cooling")])
    assert decision.stop == {A} and not decision.hold
