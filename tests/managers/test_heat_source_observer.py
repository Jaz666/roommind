"""Power evidence must not turn fan-only consumption or stale totals into delivered heat."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.roommind.managers.heat_source_observer import HeatSourceObserver


def setup():
    states = {
        "climate.trv": SimpleNamespace(state="heat", attributes={"hvac_action": "idle"}),
        "climate.ac": SimpleNamespace(state="fan_only", attributes={}),
        "sensor.ct": SimpleNamespace(state="25", attributes={"unit_of_measurement": "W"}),
        "sensor.energy": SimpleNamespace(state="1000", attributes={"unit_of_measurement": "Wh"}),
        "sensor.dehum": SimpleNamespace(state="300", attributes={"unit_of_measurement": "W"}),
    }
    hass = MagicMock()
    hass.states.get.side_effect = states.get
    room = {
        "area_id": "room",
        "devices": [
            {"entity_id": "climate.trv", "type": "trv"},
            {"entity_id": "climate.ac", "type": "ac", "energy_sensor": "sensor.energy"},
        ],
        "dehumidifier_power_sensor": "sensor.dehum",
    }
    return HeatSourceObserver(), hass, states, room, {"heat_pump_power_sensor": "sensor.ct"}


def test_meter_baseline_reset_delayed_updates_and_fan_only(monkeypatch):
    obs, hass, states, room, settings = setup()
    clock = [1000.0]
    monkeypatch.setattr("custom_components.roommind.managers.heat_source_observer.time.monotonic", lambda: clock[0])
    assert obs.energy_evidence(hass, "sensor.energy") is None
    clock[0] += 300
    states["sensor.energy"].state = "1010"
    assert obs.energy_evidence(hass, "sensor.energy") is True
    assert obs.observe(hass, room, settings, "idle") == ("radiator", 0.3)
    states["climate.ac"].state = "heat"
    states["sensor.ct"].state = "800"
    assert obs.observe(hass, room, settings, "heating")[0] is None  # mode transition straddles the last energy interval
    clock[0] += 300
    states["sensor.energy"].state = "1020"
    assert obs.observe(hass, room, settings, "heating") == ("ac", 0.3)
    states["climate.trv"].attributes["hvac_action"] = "heating"
    assert obs.observe(hass, room, settings, "heating")[0] is None
    clock[0] += 400
    states["climate.trv"].attributes["hvac_action"] = "idle"
    assert obs.observe(hass, room, settings, "heating")[0] is None
    states["sensor.energy"].state = "0"
    assert obs.energy_evidence(hass, "sensor.energy") is None
    states["sensor.energy"].state = "unavailable"
    assert obs.energy_evidence(hass, "sensor.energy") is None


def test_dehumidifier_missing_and_invalid_power_is_unknown():
    obs, hass, states, room, settings = setup()
    for value in ["unknown", "nan", "inf", "-5"]:
        states["sensor.dehum"].state = value
        assert obs.dehumidifier_kw(hass, room) is None
    states["sensor.dehum"].state = "0.3"
    states["sensor.dehum"].attributes["unit_of_measurement"] = "kW"
    assert obs.dehumidifier_kw(hass, room) == 0.3


def test_shared_ac_meter_does_not_change_radiator_only_learning():
    obs, hass, states, room, settings = setup()
    room["devices"] = room["devices"][:1]
    states["climate.trv"].attributes = {}
    states["sensor.ct"].state = "unavailable"
    assert obs.observe(hass, room, settings, "heating") == ("radiator", 0.3)
