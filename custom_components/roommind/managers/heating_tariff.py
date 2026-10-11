"""Fixed UTC electricity windows and bounded morning-target preparation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..const import TargetTemps, is_override_active
from ..utils.device_utils import get_ac_eids


def cheap_period(settings: dict, ts: float) -> tuple[bool, float]:
    """Return whether electricity is cheap, and this/next cheap period's end.

    Times are fixed UTC/GMT, deliberately independent of HA's local timezone.
    The start is inclusive and the end exclusive, including overnight windows.
    """

    def minutes(value: str) -> int:
        hour, minute = value.split(":")
        return int(hour) * 60 + int(minute)

    start = minutes(settings.get("ac_off_peak_start", "00:00"))
    end = minutes(settings.get("ac_off_peak_end", "05:00"))
    now = datetime.fromtimestamp(ts, tz=UTC)
    wall = now.hour * 60 + now.minute
    cheap = start <= wall < end if start < end else wall >= start or wall < end
    end_time = now.replace(hour=end // 60, minute=end % 60, second=0, microsecond=0)
    if end_time.timestamp() <= ts:
        end_time += timedelta(days=1)
    return cheap, end_time.timestamp()


@dataclass
class TariffDecision:
    """Room-level intent; command guards enforce the heating-only lockout."""

    heating_locked: bool = False
    boost_target: float | None = None
    boost_until: float | None = None
    cooling_floor: float | None = None
    hold_until: float | None = None
    status: str | None = None

    def targets_at(self, ts: float, normal: TargetTemps) -> TargetTemps:
        """Apply the morning band while cheap; preserve warmth afterwards."""
        if normal.heat is None and normal.cool is None:
            return normal
        heat = normal.heat
        cool = normal.cool
        if (
            self.boost_target is not None
            and self.boost_until is not None
            and ts < self.boost_until
            and heat is not None
        ):
            heat = max(heat, self.boost_target)
        if self.cooling_floor is not None and self.hold_until is not None and ts < self.hold_until and cool is not None:
            cool = max(cool, self.cooling_floor)
        return TargetTemps(heat=heat, cool=cool)


class HeatingTariffManager:
    """Choose a conservative boost and persist its post-cutoff cooling band.

    The first version uses a configurable lead time, not an uncalibrated thermal
    forecast. It never adds degrees to the morning room target. A separate device
    setpoint bias can make a Toshiba unit deliver heat despite its internal sensor.
    """

    def __init__(self) -> None:
        self.state: dict[str, dict] = {}

    def evaluate(
        self,
        room: dict,
        settings: dict,
        ts: float,
        normal: TargetTemps,
        resolver: Callable[[float], TargetTemps],
        current_temp: float | None,
        *,
        presence_away: bool = False,
    ) -> TariffDecision:
        enabled = settings.get("ac_tariff_enabled", False)
        cheap, end = cheap_period(settings, ts)
        decision = TariffDecision(heating_locked=bool(enabled and not cheap))
        area_id = room["area_id"]
        eligible = (
            enabled
            and settings.get("ac_morning_boost_enabled", False)
            and area_id in settings.get("ac_morning_boost_rooms", [])
            and get_ac_eids(room.get("devices", []))
            and room.get("temperature_sensor")
            and room.get("climate_mode", "auto") != "cool_only"
            and room.get("climate_control_enabled", True)
            and settings.get("climate_control_active", True)
            and not is_override_active(room)
            and not presence_away
            and not (settings.get("vacation_until", 0) and settings["vacation_until"] > ts)
            and normal.heat is not None
            and current_temp is not None
        )
        if not eligible:
            self.state.pop(area_id, None)
        else:
            assert normal.heat is not None
            hold = self.state.get(area_id)
            if hold and (
                ts >= hold["hold_until"]
                or hold.get("tariff")
                != [settings.get("ac_off_peak_start", "00:00"), settings.get("ac_off_peak_end", "05:00")]
            ):
                self.state.pop(area_id, None)
                hold = None
            if cheap and ts >= end - settings.get("ac_morning_boost_minutes", 30) * 60:
                # Use the first higher heating target in the six hours after the
                # cheap-rate cutoff. Constant schedules simply use today's target.
                goal = normal.heat
                cool = normal.cool
                hold_until = end
                for future in range(int(end), int(end + 6 * 3600) + 1, 60):
                    upcoming = resolver(float(future))
                    if upcoming.heat is not None and upcoming.heat > goal:
                        goal, cool, hold_until = upcoming.heat, upcoming.cool, float(future)
                        break
                # Persist a hold only while preparing a future higher target.
                # This prevents the old night cooling band undoing the preparation.
                hold = {
                    "target": goal,
                    "cool": max(goal, cool or goal),
                    "boost_until": end,
                    "hold_until": hold_until,
                    "tariff": [settings.get("ac_off_peak_start", "00:00"), settings.get("ac_off_peak_end", "05:00")],
                }
                self.state[area_id] = hold
            if hold:
                decision.boost_target = hold["target"] if cheap and ts < hold["boost_until"] else None
                decision.boost_until = hold["boost_until"]
                decision.cooling_floor = hold["cool"]
                decision.hold_until = hold["hold_until"]
                decision.status = "boost" if decision.boost_target is not None else "warmth_hold"
        if decision.status is None and decision.heating_locked and get_ac_eids(room.get("devices", [])):
            decision.status = "peak"
        return decision
