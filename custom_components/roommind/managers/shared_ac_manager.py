"""Resolve shared outdoor-unit direction before applying any room commands."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..utils.device_utils import get_ac_eids


@dataclass
class SharedACDecision:
    """A direction permission, never a request to start every indoor unit."""

    action: str = "idle"
    reason: str = ""
    owned: set[str] = field(default_factory=set)
    stop: set[str] = field(default_factory=set)
    hold: set[str] = field(default_factory=set)


class SharedACManager:
    """Coordinate explicit heat/cool modes, with reported-off changeovers.

    Timing follows selected modes, not measured compressor operation. Unknown
    status prevents a new direction; disabled/unmanaged units are never written.
    UTC timestamps survive reloads while the bedtime rule uses HA local time.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.state: dict[str, dict] = {}
        self.decisions: dict[str, SharedACDecision] = {}

    def resolve(self, groups: list[dict], prepared: list[dict]) -> None:
        now = time.time()
        hour = dt_util.now().hour
        night = hour >= 22 or hour < 7
        self.decisions = {}
        configured = {g["id"] for g in groups if g.get("shared_ac_control", False)}
        self.state = {gid: value for gid, value in self.state.items() if gid in configured}
        for group in groups:
            if group["id"] not in configured:
                continue
            members = set(group["members"])
            owned: set[str] = set()
            urgent_stop: set[str] = set()
            requests: dict[str, str] = {}
            for item in prepared:
                if not item.get("prepared") or not item["commandable"]:
                    continue
                urgent_stop.update(set(item.get("stop_entities", set())) & members)
                for eid in members & set(get_ac_eids(item["room"].get("devices", []))):
                    owned.add(eid)
                    if item.get("stop_immediately"):
                        urgent_stop.add(eid)
                    if item["mode"] in ("heating", "cooling"):
                        requests[eid] = "heat" if item["mode"] == "heating" else "cool"
            modes: dict[str, str] = {}
            unknown = False
            for eid in members:
                value = self.hass.states.get(eid)
                supported = value.attributes.get("hvac_modes") if value is not None else None
                if isinstance(supported, (list, tuple)) and not {"heat", "cool"} <= set(supported):
                    unknown = True
                if value is None or value.state not in ("off", "fan_only", "heat", "cool", "dry"):
                    unknown = True
                elif value.state not in ("off", "fan_only"):
                    modes[eid] = "cool" if value.state == "dry" else value.state
            decision = SharedACDecision(owned=owned)
            previous = self.state.get(group["id"], {})
            if previous.get("members") != sorted(members):
                previous = {**previous, "members": sorted(members)}
            self.state[group["id"]] = previous
            external = set(modes) - owned
            if unknown or len(set(modes.values())) > 1:
                decision.reason = "unknown_status" if unknown else "conflicting_modes"
                decision.stop = set(modes) & owned
                previous["stopping"] = True
            elif external:
                # An independently controlled unit determines the permissible
                # direction until it stops; RoomMind cannot change it safely.
                decision.action = modes[next(iter(external))]
                decision.reason = "external_control"
            else:
                cool = {eid for eid, mode in requests.items() if mode == "cool"}
                heat = set(requests) - cool
                bedtime_cool = night and bool(cool & set(group.get("night_cooling_members", [])))
                desired = "cool" if cool and (bedtime_cool or not heat) else "heat" if heat else "idle"
                if modes:
                    observed = next(iter(modes.values()))
                    if previous.get("direction") != observed:
                        previous.update(direction=observed, on_since=now)
                    previous["start_until"] = 0
                    elapsed = now - previous.get("on_since", now)
                    if previous.get("stopping") or (
                        desired != observed and elapsed >= group.get("min_run_minutes", 5) * 60
                    ):
                        previous["stopping"] = True
                        decision.stop = set(modes) & owned
                        decision.reason = "changeover"
                    else:
                        decision.action = observed
                        if desired != observed:
                            decision.hold = set(modes) & owned
                            decision.reason = "minimum_run"
                elif previous.get("start_until", 0) > now:
                    # Cloud mode reports lag a command. Do not reverse a
                    # just-started direction based on an old 'off' report.
                    decision.action = previous["direction"]
                    if desired != decision.action or previous.get("stopping"):
                        previous["stopping"] = True
                        decision.action = "idle"
                        decision.stop = owned.copy()
                    decision.reason = "awaiting_status"
                else:
                    if previous.get("direction") or previous.pop("stopping", False):
                        previous.update(direction=None, on_since=None, off_since=now)
                        previous["stopping"] = False
                    since = previous.get("off_since")
                    if since is not None and now - since < group.get("min_off_minutes", 5) * 60:
                        decision.reason = "minimum_off"
                    else:
                        decision.action = desired
                        if desired != "idle":
                            previous.update(direction=desired, on_since=now, start_until=now + 90)
            decision.stop.update(urgent_stop & set(modes))
            decision.hold -= urgent_stop
            for eid in members:
                self.decisions[eid] = decision

    def blocked(self, eid: str, mode: str) -> bool:
        """Whether this device may satisfy the room's requested direction."""
        decision = self.decisions.get(eid)
        return (
            decision is not None
            and mode in ("heating", "cooling")
            and decision.action != ("heat" if mode == "heating" else "cool")
        )
