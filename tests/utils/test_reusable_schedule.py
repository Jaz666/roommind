"""Reusable schedules validate before activation and resolve in HA local time."""

from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.roommind.utils.reusable_schedule import WEEKDAYS, schedule_summary, validate_schedule
from custom_components.roommind.utils.schedule_utils import find_active_block, make_target_resolver


def week():
    return {
        day: [
            {"from": "00:00", "to": "07:00", "data": {"heat_temperature": 19, "cool_temperature": 19.5}},
            {"from": "07:00", "to": "22:00", "data": {"heat_temperature": 20, "cool_temperature": 20.5}},
            {"from": "22:00", "to": "24:00", "data": {"heat_temperature": 19, "cool_temperature": 19.5}},
        ]
        for day in WEEKDAYS
    }


def test_full_week_and_midnight():
    schedule = validate_schedule(" Bedrooms ", week())
    assert schedule["name"] == "Bedrooms"
    assert schedule["days"]["monday"][-1]["to"] == "24:00:00"
    for hour, expected in [(0, 19), (6, 19), (7, 20), (21, 20), (22, 19), (23, 19)]:
        ts = datetime(2026, 7, 6, hour, 59, tzinfo=ZoneInfo("UTC")).timestamp()
        assert find_active_block(schedule["days"], ts)["heat_temperature"] == expected


@pytest.mark.parametrize(
    "mutation",
    [
        lambda days: days.pop("sunday"),
        lambda days: days.update(other=[]),
        lambda days: days.update(monday=[]),
        lambda days: days["monday"][0].update(to="07:01"),
        lambda days: days["monday"][1].update(to="06:00"),
        lambda days: days["monday"][-1].update(to="23:59"),
        lambda days: days["monday"][0].update(**{"from": "24:00"}),
        lambda days: days["monday"][0].update(to="07:60"),
        lambda days: days["monday"][0].update(to="07:00:30"),
        lambda days: days["monday"][0].update(extra=1),
        lambda days: days["monday"][0].update(data=None),
        lambda days: days["monday"][0]["data"].update(heat_temperature=36),
        lambda days: days["monday"][0]["data"].update(cool_temperature=float("nan")),
        lambda days: days["monday"][0]["data"].update(cool_temperature=float("inf")),
        lambda days: days["monday"][0]["data"].update(heat_temperature=True),
        lambda days: days["monday"][0]["data"].update(cool_temperature=18),
    ],
)
def test_invalid_schedule_cannot_activate(mutation):
    days = week()
    mutation(days)
    with pytest.raises(ValueError):
        validate_schedule("Bedrooms", days)


@pytest.mark.parametrize("name", ["", "   ", "a" * 81])
def test_name_required(name):
    with pytest.raises(ValueError):
        validate_schedule(name, week())


def test_dst_and_next_change():
    dt_util.set_default_time_zone(ZoneInfo("Europe/London"))
    days = {
        day: [
            {"from": "00:00", "to": "01:30", "data": {"heat_temperature": 19, "cool_temperature": 19.5}},
            {"from": "01:30", "to": "24:00", "data": {"heat_temperature": 20, "cool_temperature": 20.5}},
        ]
        for day in WEEKDAYS
    }
    schedule = {**validate_schedule("DST", days), "id": "dst"}
    # Spring's missing 01:30 block begins at the actual 02:00 clock jump.
    now = datetime(2026, 3, 29, 0, 45, tzinfo=ZoneInfo("UTC")).timestamp()
    summary = schedule_summary(schedule, now)
    assert summary["next_change"] == datetime(2026, 3, 29, 1, tzinfo=ZoneInfo("UTC")).timestamp()
    assert summary["next_targets"]["heat_temperature"] == 20
    # Fall: after the first 01:30, the clock returns to the earlier block.
    now = datetime(2026, 10, 25, 0, 45, tzinfo=ZoneInfo("UTC")).timestamp()
    summary = schedule_summary(schedule, now)
    assert summary["targets"]["heat_temperature"] == 20
    assert summary["next_change"] == datetime(2026, 10, 25, 1, tzinfo=ZoneInfo("UTC")).timestamp()
    assert summary["next_targets"]["heat_temperature"] == 19
    summary = schedule_summary(schedule, summary["next_change"])
    assert summary["next_change"] == datetime(2026, 10, 25, 1, 30, tzinfo=ZoneInfo("UTC")).timestamp()


def test_constant_week_has_no_change():
    days = {
        day: [{"from": "00:00", "to": "24:00", "data": {"heat_temperature": 20, "cool_temperature": 20.5}}]
        for day in WEEKDAYS
    }
    summary = schedule_summary(
        {**validate_schedule("Constant", days), "id": "constant"},
        datetime(2026, 10, 11, tzinfo=ZoneInfo("UTC")).timestamp(),
    )
    assert summary["next_change"] is None


def test_future_resolver_keeps_internal_celsius_even_on_fahrenheit(hass):
    hass.config.units.temperature_unit = "°F"
    days = validate_schedule("Rooms", week())["days"]
    room = {"roommind_schedule_id": "rooms", "comfort_heat": 21, "comfort_cool": 24}
    resolver = make_target_resolver(days, room, {}, hass=hass)
    assert resolver(datetime(2026, 7, 6, 8, tzinfo=ZoneInfo("UTC")).timestamp()).heat == 20
    assert resolver(datetime(2026, 7, 6, 23, tzinfo=ZoneInfo("UTC")).timestamp()).cool == 19.5
    room.update(override_heat=22, override_cool=23, override_until=None)
    resolver = make_target_resolver(deepcopy(days), room, {}, hass=hass)
    assert resolver(datetime(2026, 7, 6, 23, tzinfo=ZoneInfo("UTC")).timestamp()).heat == 22


def test_import_helper_fills_gaps_and_converts_units():
    from custom_components.roommind.utils.reusable_schedule import import_helper_blocks

    blocks = {
        "monday": [{"from": "07:00:00", "to": "22:00:00", "data": {"heat_temperature": 68, "cool_temperature": 69.8}}]
    }
    imported = import_helper_blocks("Imported", blocks, 19, 19.5, lambda f: (f - 32) * 5 / 9)
    monday = imported["days"]["monday"]
    assert len(monday) == 3
    assert monday[0]["data"]["heat_temperature"] == 19
    assert monday[1]["data"]["heat_temperature"] == 20
    assert monday[1]["data"]["cool_temperature"] == pytest.approx(21)
    assert monday[2]["to"] == "24:00:00"
    assert imported["days"]["sunday"][0]["data"]["heat_temperature"] == 19


def test_import_helper_midnight_end_and_invalid_band():
    from custom_components.roommind.utils.reusable_schedule import import_helper_blocks

    blocks = {"monday": [{"from": "00:00:00", "to": "00:00:00", "data": {"temperature": 20}}]}
    imported = import_helper_blocks("Imported", blocks, 19, 19.5, lambda c: c)
    assert imported["days"]["monday"][0]["to"] == "24:00:00"
    assert imported["days"]["monday"][0]["data"]["cool_temperature"] == 20
    blocks["monday"][0]["data"] = {"heat_temperature": 21, "cool_temperature": 19}
    with pytest.raises(ValueError, match="cool target"):
        import_helper_blocks("Imported", blocks, 19, 19.5, lambda c: c)
