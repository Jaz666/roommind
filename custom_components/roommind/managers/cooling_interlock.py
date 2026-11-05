"""Opt-in heating inhibition for rooms with independently controlled cooling."""

from __future__ import annotations

import time

from homeassistant.core import HomeAssistant


class CoolingInterlock:
    """Watch cooling modes without taking ownership of the monitored devices.

    A selected cool/dry mode inhibits heat even if the compressor is currently
    idle: a thermostat can resume cooling without another mode change. Toshiba
    only reports the selected mode, not the actual compressor action.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._active: set[str] = set()
        self._recovery_since: dict[str, float] = {}
        self._entities: dict[str, tuple[str, ...]] = {}

    def evaluate(
        self,
        room: dict,
        *,
        commanded_cooling: bool,
        current_temp: float | None,
        heat_target: float | None,
    ) -> str | None:
        """Return the heating block reason, or None when heat is permitted."""
        area_id = room["area_id"]
        entities = tuple(sorted(set(room.get("cooling_interlock_entities", []))))
        if not entities:
            self.remove_room(area_id)
            return None
        # Editing the monitor list must not inherit another device's latch.
        if self._entities.get(area_id) != entities:
            self.remove_room(area_id)
            self._entities[area_id] = entities

        cooling = commanded_cooling
        unavailable = False
        for eid in entities:
            state = self._hass.states.get(eid)
            if state is None or state.state in ("unknown", "unavailable"):
                unavailable = True
            elif state.state in ("cool", "dry") or state.attributes.get("hvac_action") in (
                "cooling",
                "drying",
            ):
                cooling = True
            elif state.state in ("auto", "heat_cool"):
                # Auto may start cooling without a selected-mode update.
                # Require explicit heat/off/fan mode before allowing heat.
                unavailable = True

        if cooling:
            self._active.add(area_id)
            self._recovery_since.pop(area_id, None)
            return "cooling"
        if unavailable:
            # Start recovery only after cooling status is known again.
            self._active.add(area_id)
            self._recovery_since.pop(area_id, None)
            return "cooling_status_unknown"

        if area_id in self._active:
            self._active.remove(area_id)
            self._recovery_since[area_id] = time.time()
        since = self._recovery_since.get(area_id)
        if since is None:
            return None
        delay = room.get("cooling_interlock_delay", 300)
        if time.time() - since < delay:
            return "recovery"
        if current_temp is None or heat_target is None:
            return "recovery"
        margin = room.get("cooling_interlock_deadband", 0.3)
        if current_temp >= heat_target - margin:
            return "recovery"
        self._recovery_since.pop(area_id)
        return None

    def get_state(self) -> dict:
        """Persist the recovery latch across HA restarts using UTC timestamps."""
        return {
            "active": sorted(self._active),
            "recovery_since": dict(self._recovery_since),
            "entities": {key: list(value) for key, value in self._entities.items()},
        }

    def load_state(self, state: dict) -> None:
        """Restore a previously saved monitor/recovery state."""
        self._active = set(state.get("active", []))
        self._recovery_since = dict(state.get("recovery_since", {}))
        self._entities = {key: tuple(value) for key, value in state.get("entities", {}).items()}

    def remove_room(self, area_id: str) -> None:
        """Forget a removed/disabled room's monitor and recovery latch."""
        self._active.discard(area_id)
        self._recovery_since.pop(area_id, None)
        self._entities.pop(area_id, None)
