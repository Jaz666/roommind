"""Fixed-GMT tariff boundaries and morning comfort preparation."""

from datetime import datetime

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.managers.heating_tariff import HeatingTariffManager, cheap_period


def ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


ROOM = {
    "area_id": "living",
    "temperature_sensor": "sensor.external",
    "devices": [{"entity_id": "climate.ac", "type": "ac"}],
}
SETTINGS = {"ac_tariff_enabled": True, "ac_morning_boost_enabled": True, "ac_morning_boost_rooms": ["living"]}
NIGHT = TargetTemps(heat=19, cool=19.5)
MORNING = TargetTemps(heat=21, cool=21.5)


@pytest.mark.parametrize("date", ["2026-01-01", "2026-07-01"])
@pytest.mark.parametrize(
    "time,expected", [("00:00:00", True), ("04:59:59", True), ("05:00:00", False), ("23:59:59", False)]
)
def test_fixed_gmt_boundaries(date, time, expected):
    assert cheap_period({}, ts(f"{date}T{time}Z"))[0] is expected


@pytest.mark.parametrize("time,expected", [("22:59", False), ("23:00", True), ("01:59", True), ("02:00", False)])
def test_midnight_crossing(time, expected):
    assert (
        cheap_period({"ac_off_peak_start": "23:00", "ac_off_peak_end": "02:00"}, ts(f"2026-01-01T{time}:00Z"))[0]
        is expected
    )


def test_boost_caps_at_morning_target_and_preserves_warmth_after_restart():
    manager = HeatingTariffManager()
    morning = ts("2026-07-01T06:00:00Z")  # 07:00 BST

    def resolver(now):
        return MORNING if now >= morning else NIGHT

    before = manager.evaluate(ROOM, SETTINGS, ts("2026-07-01T04:29:59Z"), NIGHT, resolver, 18)
    assert before.boost_target is None
    boost = manager.evaluate(ROOM, SETTINGS, ts("2026-07-01T04:30:00Z"), NIGHT, resolver, 18)
    assert boost.targets_at(ts("2026-07-01T04:59:59Z"), NIGHT) == MORNING
    assert boost.boost_target == 21
    reloaded = HeatingTariffManager()
    reloaded.state = manager.state.copy()
    peak = reloaded.evaluate(ROOM, SETTINGS, ts("2026-07-01T05:00:00Z"), NIGHT, resolver, 21)
    assert peak.heating_locked and peak.boost_target is None and peak.status == "warmth_hold"
    assert peak.targets_at(ts("2026-07-01T05:30:00Z"), NIGHT) == TargetTemps(heat=19, cool=21.5)
    assert peak.targets_at(morning, MORNING) == MORNING
    reloaded.evaluate(ROOM, SETTINGS, morning, MORNING, resolver, 21)
    assert not reloaded.state


@pytest.mark.parametrize(
    "room_change,settings_change,away",
    [
        ({"temperature_sensor": ""}, {}, False),
        ({"devices": []}, {}, False),
        ({"climate_mode": "cool_only"}, {}, False),
        ({"climate_control_enabled": False}, {}, False),
        ({"override_type": "custom", "override_heat": 20, "override_until": 9999999999}, {}, False),
        ({}, {"climate_control_active": False}, False),
        ({}, {"ac_tariff_enabled": False}, False),
        ({}, {"vacation_until": 9999999999}, False),
        ({}, {}, True),
    ],
)
def test_manual_and_absence_choices_cancel_preparation(room_change, settings_change, away):
    manager = HeatingTariffManager()
    now = ts("2026-01-01T04:45:00Z")
    manager.evaluate(ROOM, SETTINGS, now, NIGHT, lambda _: MORNING, 18)
    decision = manager.evaluate(
        {**ROOM, **room_change}, {**SETTINGS, **settings_change}, now, NIGHT, lambda _: MORNING, 18, presence_away=away
    )
    assert decision.boost_target is None and not manager.state


def test_constant_schedule_uses_current_target_and_off_stays_off():
    manager = HeatingTariffManager()
    now = ts("2026-01-01T04:45:00Z")
    result = manager.evaluate(ROOM, SETTINGS, now, MORNING, lambda _: MORNING, 18)
    assert result.boost_target == 21 and result.targets_at(now, MORNING) == MORNING
    assert result.targets_at(now, TargetTemps(heat=None, cool=None)) == TargetTemps(heat=None, cool=None)


@pytest.mark.parametrize("margin", [0, 0.2, 0.5])
def test_early_stop_and_restart_hysteresis_survive_repeated_updates(margin):
    manager = HeatingTariffManager()
    settings = {**SETTINGS, "ac_morning_boost_stop_margin": margin}
    now = ts("2026-07-01T04:45:00Z")
    stop = MORNING.heat - margin
    result = manager.evaluate(ROOM, settings, now, MORNING, lambda _: MORNING, stop)
    assert result.heating_paused
    result = manager.evaluate(ROOM, settings, now + 60, MORNING, lambda _: MORNING, stop - 0.1)
    assert result.heating_paused
    result = manager.evaluate(ROOM, settings, now + 120, MORNING, lambda _: MORNING, stop - 0.4)
    assert not result.heating_paused


def test_constant_equal_targets_keep_bounded_cooling_band_after_cutoff():
    manager = HeatingTariffManager()
    target = TargetTemps(heat=20, cool=20)
    manager.evaluate(ROOM, SETTINGS, ts("2026-07-01T04:45:00Z"), target, lambda _: target, 19)
    cutoff = ts("2026-07-01T05:00:00Z")
    result = manager.evaluate(ROOM, SETTINGS, cutoff, target, lambda _: target, 20.2)
    assert result.status == "warmth_hold"
    assert result.targets_at(cutoff, target) == TargetTemps(heat=20, cool=20.5)
    expired = manager.evaluate(ROOM, SETTINGS, cutoff + 1800, target, lambda _: target, 20.2)
    assert expired.targets_at(cutoff + 1800, target) == target
    assert not manager.state


def test_schedule_at_cutoff_keeps_short_handover_even_if_heat_target_unchanged():
    manager = HeatingTariffManager()
    now = ts("2026-07-01T04:45:00Z")
    cutoff = ts("2026-07-01T05:00:00Z")

    def resolver(future):
        return MORNING if future >= cutoff else NIGHT

    manager.evaluate(ROOM, SETTINGS, now, NIGHT, resolver, 19)
    result = manager.evaluate(ROOM, SETTINGS, cutoff, MORNING, resolver, 21.2)
    assert result.status == "warmth_hold"
    assert result.hold_until == cutoff + 1800


def test_legacy_constant_hold_is_upgraded_at_cutoff():
    manager = HeatingTariffManager()
    cutoff = ts("2026-07-01T05:00:00Z")
    manager.state["living"] = {
        "target": 20,
        "cool": 20,
        "boost_until": cutoff,
        "hold_until": cutoff,
        "tariff": ["00:00", "05:00"],
    }
    target = TargetTemps(heat=20, cool=20)
    result = manager.evaluate(ROOM, SETTINGS, cutoff + 60, target, lambda _: target, 20.2)
    assert result.targets_at(cutoff + 60, target).cool == 20.5
    assert result.status == "warmth_hold"
