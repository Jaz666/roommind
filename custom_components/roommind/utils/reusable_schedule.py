"""Validated, reusable weekly comfort schedules (stored in Celsius)."""

from __future__ import annotations

import copy
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .schedule_utils import find_active_block, sanitize_block_temp

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def time_minutes(value: Any) -> int:
    """Parse minute-resolution wall time; 24:00 is an end boundary."""
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::00)?|24:00(?::00)?", value):
        raise ValueError("Use times from 00:00 to 24:00, in whole minutes.")
    return int(value[:2]) * 60 + int(value[3:5])


def validate_schedule(name: str, days: dict) -> dict:
    """Validate full-week coverage, chronological blocks and comfort bands."""
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ValueError("Give the schedule a name of up to 80 characters.")
    if not isinstance(days, dict) or set(days) != set(WEEKDAYS):
        raise ValueError("A schedule must contain all seven days.")
    result: dict = {"name": name.strip(), "days": {}}
    for day in WEEKDAYS:
        blocks = days[day]
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= 48:
            raise ValueError(f"{day.title()}: use between 1 and 48 blocks.")
        expected = 0
        cleaned = []
        for block in blocks:
            if not isinstance(block, dict) or set(block) != {"from", "to", "data"}:
                raise ValueError(f"{day.title()}: invalid block.")
            start, end = time_minutes(block["from"]), time_minutes(block["to"])
            if start != expected or end <= start:
                raise ValueError(f"{day.title()}: blocks must cover midnight to midnight without gaps or overlaps.")
            data = block["data"]
            if not isinstance(data, dict) or set(data) != {"heat_temperature", "cool_temperature"}:
                raise ValueError(f"{day.title()}: each block needs heat and cool targets.")
            heat = sanitize_block_temp(data["heat_temperature"])
            cool = sanitize_block_temp(data["cool_temperature"])
            if (
                isinstance(data["heat_temperature"], bool)
                or isinstance(data["cool_temperature"], bool)
                or heat is None
                or cool is None
            ):
                raise ValueError(f"{day.title()}: temperatures must be between 5 and 35 °C.")
            if heat > cool:
                raise ValueError(f"{day.title()}: the cool target must be at least the heat target.")
            cleaned.append(
                {
                    "from": f"{start // 60:02d}:{start % 60:02d}:00",
                    "to": f"{end // 60:02d}:{end % 60:02d}:00",
                    "data": {"heat_temperature": heat, "cool_temperature": cool},
                }
            )
            expected = end
        if expected != 1440:
            raise ValueError(f"{day.title()}: the last block must end at 24:00.")
        result["days"][day] = cleaned
    return result


def schedule_summary(schedule: dict, ts: float) -> dict:
    """Describe current scheduled targets and the next real target change.

    Consider local block boundaries and UTC offset changes to handle skipped
    and repeated local times at daylight-saving transitions. Schedules
    use HA's timezone, independently of any future UTC electricity tariff.
    """
    days = schedule["days"]
    active = find_active_block(days, ts)
    next_change = None
    next_targets = None
    # Look far enough ahead to include the next instance of today's blocks.
    # A constant weekly schedule has no next change.
    local_now = dt_util.as_local(datetime.fromtimestamp(ts, tz=UTC))
    tz = dt_util.get_default_time_zone()
    candidates: set[float] = set()
    for offset in range(9):
        date = local_now.date() + timedelta(days=offset)
        day = WEEKDAYS[date.weekday()]
        for block in days[day]:
            minutes = time_minutes(block["from"])
            naive = datetime.combine(date, datetime.min.time()) + timedelta(minutes=minutes)
            for fold in (0, 1):
                candidates.add(naive.replace(tzinfo=tz, fold=fold).timestamp())
    # DST jumps can cross a block whose nominal boundary doesn't exist. Include
    # offset-change minutes so the summary agrees with timestamp resolution.
    previous_offset = local_now.utcoffset()
    hour = int(ts // 3600) * 3600 + 3600
    for timestamp in range(hour, hour + 8 * 24 * 60 * 60, 3600):
        offset = dt_util.as_local(datetime.fromtimestamp(timestamp, tz=UTC)).utcoffset()
        if offset != previous_offset:
            for boundary in range(max(int(ts // 60) * 60 + 60, timestamp - 3600), timestamp + 60, 60):
                new_offset = dt_util.as_local(datetime.fromtimestamp(boundary, tz=UTC)).utcoffset()
                if new_offset != previous_offset:
                    candidates.add(float(boundary))
                    break
        previous_offset = offset
    for candidate in sorted(candidates):
        if candidate <= ts:
            continue
        targets = find_active_block(days, candidate)
        if targets != active:
            next_change, next_targets = candidate, targets
            break
    return {
        "id": schedule["id"],
        "name": schedule["name"],
        "targets": copy.deepcopy(active),
        "next_change": next_change,
        "next_targets": next_targets,
    }


def import_helper_blocks(name: str, blocks: dict, fallback_heat: float, fallback_cool: float, converter: Any) -> dict:
    """Make a full-week draft from HA helper blocks, filling inactive periods.

    HA block data is in display units; reusable schedules always store Celsius.
    The fallback band is explicit, so helper gaps cannot become implicit heat.
    """
    days: dict = {}
    fallback = {"heat_temperature": fallback_heat, "cool_temperature": fallback_cool}
    for day in WEEKDAYS:
        source = blocks.get(day, [])
        if not isinstance(source, list):
            raise ValueError(f"{day.title()}: this helper has invalid blocks.")
        cleaned = []
        cursor = 0
        for block in sorted(source, key=lambda b: str(b.get("from", "00:00:00"))):
            start = time_minutes(str(block["from"]))
            end = time_minutes(str(block["to"])) or 1440
            if start < cursor or end <= start:
                raise ValueError(f"{day.title()}: helper blocks overlap or cross midnight.")
            if start > cursor:
                cleaned.append(
                    {
                        "from": f"{cursor // 60:02d}:{cursor % 60:02d}",
                        "to": f"{start // 60:02d}:{start % 60:02d}",
                        "data": copy.deepcopy(fallback),
                    }
                )
            data = block.get("data") or {}
            single = data.get("temperature")
            targets = {}
            for field, default in fallback.items():
                raw = data.get(field, single)
                value = sanitize_block_temp(raw, converter) if raw is not None else default
                if value is None:
                    raise ValueError(f"{day.title()}: helper contains an invalid temperature.")
                targets[field] = value
            cleaned.append(
                {
                    "from": f"{start // 60:02d}:{start % 60:02d}",
                    "to": f"{end // 60:02d}:{end % 60:02d}",
                    "data": targets,
                }
            )
            cursor = end
        if cursor < 1440:
            cleaned.append(
                {"from": f"{cursor // 60:02d}:{cursor % 60:02d}", "to": "24:00", "data": copy.deepcopy(fallback)}
            )
        days[day] = cleaned
    return validate_schedule(name, days)
