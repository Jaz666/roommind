"""Source separation, migration and setback protection against weak learned heating."""

from unittest.mock import MagicMock

import pytest

from custom_components.roommind.const import TargetTemps
from custom_components.roommind.control.mpc_controller import MPCController
from custom_components.roommind.control.thermal_model import RCModel, RoomModelManager, ThermalEKF
from custom_components.roommind.managers.ekf_training_manager import EkfTrainingManager

from .conftest import build_hass, make_room


def test_sources_learn_independently_with_shared_room_physics():
    """Alternate clean radiator/AC/dehumidifier/idle periods on one physical room."""
    true = RCModel(C=1, U=0.06, Q_heat=1.0, Q_cool=2.0, Q_solar=0, Q_occupancy=0)
    est = ThermalEKF(20)
    t = 20.0
    for step in range(2400):
        phase = (step // 40) % 4
        source = "ac" if phase == 1 else "radiator"
        mode = "heating" if phase in (0, 1) else "idle"
        kw = 0.3 if phase == 2 else 0.0
        power = (3.0 if source == "ac" else 1.0) if mode == "heating" else 0.0
        true.Q_aux = 1.2 * kw
        t = true.predict(t, 10, power, 3)
        est.update(t, 10, mode, 3, heating_source=source, dehumidifier_kw=kw)
    assert est._x[2] == pytest.approx(1.0, abs=0.2)
    assert est._x[7] == pytest.approx(3.0, abs=0.2)
    assert est._x[8] == pytest.approx(1.2, abs=0.3)
    assert est._x[1] == pytest.approx(0.06, abs=0.02)
    restored = ThermalEKF.from_dict(est.to_dict())
    assert restored._x == est._x
    assert restored._P == est._P
    assert restored._n_ac_heating == est._n_ac_heating


def test_inactive_source_does_not_learn_from_other_heater():
    est = ThermalEKF()
    est.update(20, 10, "idle", 3)
    original = est._x[2]
    for _ in range(30):
        est.update(21, 10, "heating", 3, heating_source="ac")
    assert est._x[2] == original
    ac = est._x[7]
    for _ in range(30):
        est.update(20, 10, "heating", 3, heating_source="radiator")
    assert est._x[7] == ac


def test_legacy_mixed_migration_preserves_room_physics_but_relearns_heaters():
    est = ThermalEKF()
    est._x[1:5] = [0.016, 0.227, 0.51, 0.12]
    est._n_heating = 13000
    est._n_idle = 60000
    legacy = est.to_dict()
    legacy.pop("source_model")
    migrated = ThermalEKF.from_dict(legacy)
    migrated.configure_sources(True, False)
    assert migrated._x[1] == 0.016
    assert migrated._x[3:5] == [0.51, 0.12]
    assert migrated._n_idle == 60000
    assert migrated._n_heating == migrated._n_ac_heating == 0
    migrated._x[2] = 1.5
    persisted = ThermalEKF.from_dict(migrated.to_dict())
    persisted.configure_sources(True, False)
    assert persisted._x[2] == 1.5
    single = ThermalEKF.from_dict(legacy)
    single.configure_sources(False, False)
    assert single._x[2] == 0.227
    ac = ThermalEKF.from_dict(legacy)
    ac.configure_sources(False, True)
    assert ac._x[7] == 0.227
    assert ac._n_ac_heating == 13000


def test_source_switch_discards_straddling_training_batch():
    models = RoomModelManager()
    trainer = EkfTrainingManager(models)
    args = dict(
        area_id="room",
        current_temp=20,
        T_outdoor=10,
        ekf_mode="heating",
        ekf_pf=1,
        window_open=False,
        raw_open=False,
        q_residual=0,
        shading_factor=1,
        q_solar=0,
        can_heat=True,
        can_cool=False,
        dt_minutes=1,
    )
    trainer.process(**args, heating_source="radiator")
    trainer.process(**args, heating_source="ac")
    assert not trainer._accumulated_dt
    assert models.get_n_observations("room") == 0


@pytest.mark.parametrize("hours,limit", [(2, 60), (6, 60), (8, 60), (0.25, 0)])
def test_weak_living_room_model_cannot_preheat_all_night(monkeypatch, hours, limit):
    models = RoomModelManager()
    est = models.get_estimator("living_room")
    est._x[1], est._x[2] = 0.016122, 0.22695
    now = 1000000
    monkeypatch.setattr("custom_components.roommind.control.mpc_controller.time.time", lambda: now)
    room = make_room(climate_mode="heat_only", heating_system_type="radiator", preheat_max_minutes=limit)
    hass = build_hass()
    state = MagicMock()
    state.state = "heat"
    state.attributes = {"hvac_modes": ["heat", "off"]}
    hass.states.get.return_value = state
    controller = MPCController(
        hass,
        room,
        model_manager=models,
        outdoor_temp=7.6,
        settings={"comfort_weight": 60},
        heating_system_type="radiator",
        target_resolver=lambda ts: TargetTemps(21 if ts >= now + hours * 3600 else 19, None),
    )
    mode, power = controller._evaluate_mpc(20.43, TargetTemps(19, None))
    assert (mode, power) == ("idle", 0)
    assert controller.direct_target("heating", 19) == 19


def test_dehumidifier_gain_reduces_required_heating_and_warms_idle_prediction():
    from custom_components.roommind.control.mpc_controller import valve_demand
    from custom_components.roommind.control.mpc_optimizer import MPCOptimizer

    model = RCModel(C=1, U=0.1, Q_heat=5)
    optimizer = MPCOptimizer(model, can_heat=True, can_cool=False, w_energy=0)
    without, mode = optimizer.compute_optimal_power(20, 10, 20.2, 5)
    idle_without = model.predict(20, 10, 0, 5)
    valve_without = valve_demand(model, 20, 10, 20, q_solar=0, q_occupancy=0)
    model.Q_aux = 0.5
    with_gain, mode_with = optimizer.compute_optimal_power(20, 10, 20.2, 5)
    assert mode == mode_with == "heating"
    assert with_gain < without
    assert model.predict(20, 10, 0, 5) > idle_without
    assert valve_demand(model, 20, 10, 20, q_solar=0, q_occupancy=0) < valve_without
