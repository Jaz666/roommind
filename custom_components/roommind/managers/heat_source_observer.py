"""Conservative thermal-input evidence; electricity is never treated as delivered heat."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime

from homeassistant.core import HomeAssistant

from ..utils.device_utils import get_ac_eids, get_trv_eids


def sensor_number(hass: HomeAssistant, entity_id: str, units: tuple[str, ...]) -> float | None:
    """Read a finite, nonnegative measurement with the expected unit."""
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.attributes.get("unit_of_measurement") not in units:
        return None
    reported = getattr(state, "last_reported", None)
    if "Wh" not in units and isinstance(reported, datetime) and (datetime.now(UTC) - reported).total_seconds() > 300:
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


class HeatSourceObserver:
    """Identify clean single-source intervals, retaining uncertainty for mixed inputs."""

    def __init__(self) -> None:
        self._energy: dict[str, tuple[float, float, float]] = {}
        self._energy_modes: dict[str, str] = {}
        self._fan_watts: dict[str, float] = {}
        self._last_source: dict[str, str] = {}
        self.observed_modes: dict[str, str] = {}

    def dehumidifier_kw(self, hass: HomeAssistant, room: dict) -> float | None:
        """Measured input in kW; missing configured telemetry must not become zero."""
        eid = room.get("dehumidifier_power_sensor", "")
        if not eid:
            return 0.0
        watts = sensor_number(hass, eid, ("W", "kW"))
        if watts is None:
            return None
        state = hass.states.get(eid)
        return watts if state.attributes["unit_of_measurement"] == "kW" else watts / 1000.0

    def energy_evidence(self, hass: HomeAssistant, entity_id: str, hvac_mode: str = "heat") -> bool | None:
        """Recent energy increase supports activity; a flat/reset counter proves nothing.

        Irregular updates are averaged over their observation interval, never used
        as instantaneous watts. Reject gaps over 30 minutes and age evidence out.
        """
        value = sensor_number(hass, entity_id, ("Wh", "kWh"))
        if value is None:
            self._energy.pop(entity_id, None)
            return None
        if hass.states.get(entity_id).attributes["unit_of_measurement"] == "kWh":
            value *= 1000
        now = time.monotonic()
        old = self._energy.get(entity_id)
        changed_mode = self._energy_modes.get(entity_id, hvac_mode) != hvac_mode
        self._energy_modes[entity_id] = hvac_mode
        if old is None or value < old[0] or changed_mode:
            self._energy[entity_id] = (value, now, 0.0)
            return None
        previous, since, confirmed = old
        if value > previous:
            elapsed = now - since
            valid_interval = 30 <= elapsed <= 1800
            watts = (value - previous) * 3600 / elapsed if elapsed > 0 else 0.0
            if valid_interval and hvac_mode == "fan_only":
                previous_baseline = self._fan_watts.get(entity_id, watts)
                self._fan_watts[entity_id] = 0.8 * previous_baseline + 0.2 * watts
            baseline = self._fan_watts.get(entity_id)
            threshold = baseline + max(5.0, baseline * 0.2) if baseline is not None else 50.0
            active = valid_interval and hvac_mode == "heat" and watts > threshold
            self._energy[entity_id] = (value, now, now if active else 0.0)
            return True if active else None
        return True if hvac_mode == "heat" and confirmed and now - confirmed <= 300 else None

    def observe(
        self, hass: HomeAssistant, room: dict, settings: dict, mode: str | None
    ) -> tuple[str | None, float | None]:
        """Return heating source and auxiliary kW, or unknown for contaminated intervals."""
        self.observed_modes.pop(room["area_id"], None)
        auxiliary = self.dehumidifier_kw(hass, room)
        mixed = bool(get_trv_eids(room.get("devices", [])) and get_ac_eids(room.get("devices", [])))
        has_meter = bool(settings.get("heat_pump_power_sensor"))
        if not mixed and (not has_meter or not get_ac_eids(room.get("devices", []))):
            return ("ac" if get_ac_eids(room.get("devices", [])) else "radiator"), auxiliary
        running: set[str] = set()
        directions: set[str] = set()
        uncertain = False
        for device in room.get("devices", []):
            state = hass.states.get(device["entity_id"])
            if state is None or state.state in ("unknown", "unavailable"):
                uncertain = True
                continue
            energy = None
            if device.get("type") == "ac":
                energy = self.energy_evidence(hass, device.get("energy_sensor", ""), state.state)
            if state.state in ("off", "fan_only"):
                continue
            action = state.attributes.get("hvac_action")
            if action in ("idle", "off", "defrosting"):
                continue
            source = "ac" if device.get("type") == "ac" else "radiator"
            if action in ("heating", "preheating", "cooling"):
                running.add(source)
                directions.add("cooling" if action == "cooling" else "heating")
            elif source == "ac" and state.state == "heat":
                watts = sensor_number(hass, settings.get("heat_pump_power_sensor", ""), ("W",))
                if watts is not None and watts >= settings.get("heat_pump_active_watts", 150) and energy:
                    running.add(source)
                    directions.add("heating")
                else:
                    uncertain = True
            elif mode == "heating" or state.state in ("auto", "dry", "heat_cool", "cool"):
                uncertain = True
        area = room["area_id"]
        if len(running) > 1 or len(directions) > 1 or uncertain:
            return None, auxiliary
        if running:
            source = next(iter(running))
            self.observed_modes[area] = next(iter(directions))
            self._last_source[area] = source
            return source, auxiliary
        self.observed_modes[area] = "idle"
        return self._last_source.get(area, "radiator"), auxiliary
