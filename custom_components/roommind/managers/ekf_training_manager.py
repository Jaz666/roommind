"""EKF training accumulation and batching for RoomMind."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..const import EKF_UPDATE_MIN_DT

if TYPE_CHECKING:
    from ..control.thermal_model import RoomModelManager

_LOGGER = logging.getLogger(__name__)


class EkfTrainingManager:
    """Manages EKF training accumulation and batched updates per room."""

    def __init__(self, model_manager: RoomModelManager) -> None:
        self._model_manager = model_manager
        self._accumulated_dt: dict[str, float] = {}
        self._accumulated_mode: dict[str, str] = {}
        self._accumulated_pf: dict[str, float] = {}
        # dt-weighted mean AC rebound charge of the batch: it decays within minutes,
        # so the value at flush time would understate the batch.
        self._accumulated_rebound: dict[str, float] = {}
        self.last_temps: dict[str, float] = {}
        self._sources: dict[str, str] = {}
        self._aux: dict[str, float] = {}

    def set_model_manager(self, model_manager: RoomModelManager) -> None:
        """Update the model manager reference (used after full thermal reset)."""
        self._model_manager = model_manager

    def flush(
        self,
        area_id: str,
        current_temp: float,
        T_outdoor: float,
        can_heat: bool,
        can_cool: bool,
        q_solar: float,
        q_residual: float = 0.0,
        shading_factor: float = 1.0,
        q_occupancy: float = 0.0,
    ) -> None:
        """Flush accumulated EKF update (on mode change or window open)."""
        accumulated = self._accumulated_dt.pop(area_id, 0.0)
        prev_mode = self._accumulated_mode.pop(area_id, None)
        pf = self._accumulated_pf.pop(area_id, 1.0)
        q_rebound = self._accumulated_rebound.pop(area_id, None)
        source = self._sources.pop(area_id, "radiator")
        auxiliary = self._aux.pop(area_id, 0.0)
        if accumulated > 0 and prev_mode is not None:
            self._model_manager.update(
                area_id,
                current_temp,
                T_outdoor,
                prev_mode,
                accumulated,
                can_heat=can_heat,
                can_cool=can_cool,
                power_fraction=pf,
                q_solar=q_solar * shading_factor,
                q_residual=q_residual,
                q_occupancy=q_occupancy,
                q_rebound=q_rebound,
                heating_source=source,
                dehumidifier_kw=auxiliary,
            )

    def process(
        self,
        area_id: str,
        current_temp: float,
        T_outdoor: float,
        ekf_mode: str | None,
        ekf_pf: float,
        window_open: bool,
        raw_open: bool,
        q_residual: float,
        shading_factor: float,
        q_solar: float,
        can_heat: bool,
        can_cool: bool,
        dt_minutes: float,
        q_occupancy: float = 0.0,
        q_rebound: float | None = None,
        heating_source: str = "radiator",
        dehumidifier_kw: float = 0.0,
    ) -> None:
        """Process an EKF training step for a room.

        Contains the full training decision tree: window open, raw open
        (within delay), unobservable mode, or normal accumulation.
        """
        source_changed = self._sources.get(area_id, heating_source) != heating_source
        auxiliary_changed = abs(self._aux.get(area_id, dehumidifier_kw) - dehumidifier_kw) > 0.03
        if source_changed or auxiliary_changed:
            # The observation straddles a source/input change. Drop it rather than
            # flushing the new temperature against the previous source's parameters.
            self.clear(area_id)
            self._model_manager.sync_temperature(area_id, current_temp)
            self.last_temps[area_id] = current_temp
            return
        if window_open or raw_open:
            self.flush(
                area_id,
                current_temp,
                T_outdoor,
                can_heat,
                can_cool,
                q_solar,
                q_residual=q_residual,
                shading_factor=shading_factor,
                q_occupancy=q_occupancy,
            )
            self.clear(area_id)
            # Always track temperature state to prevent stale _x[0]
            # when normal learning resumes.  Only learn k_window when
            # the signal is clean (no residual heat).
            self._model_manager.update_window_open(
                area_id,
                current_temp,
                T_outdoor,
                dt_minutes,
                learn_k_window=(window_open and q_residual == 0.0),
            )
        elif ekf_mode is None:
            self.flush(
                area_id,
                current_temp,
                T_outdoor,
                can_heat,
                can_cool,
                q_solar,
                q_residual=q_residual,
                shading_factor=shading_factor,
                q_occupancy=q_occupancy,
            )
            self.clear(area_id)
        else:
            prev_mode = self._accumulated_mode.get(area_id)
            if prev_mode is not None and prev_mode != ekf_mode:
                self.flush(
                    area_id,
                    current_temp,
                    T_outdoor,
                    can_heat,
                    can_cool,
                    q_solar,
                    q_residual=q_residual,
                    shading_factor=shading_factor,
                    q_occupancy=q_occupancy,
                )

            self._sources[area_id] = heating_source
            old_dt = self._accumulated_dt.get(area_id, 0.0)
            new_dt = old_dt + dt_minutes
            if new_dt > 0:
                self._aux[area_id] = (
                    self._aux.get(area_id, dehumidifier_kw) * old_dt + dehumidifier_kw * dt_minutes
                ) / new_dt
                old_pf = self._accumulated_pf.get(area_id, 1.0)
                self._accumulated_pf[area_id] = (old_pf * old_dt + ekf_pf * dt_minutes) / new_dt
                if q_rebound is None:
                    self._accumulated_rebound.pop(area_id, None)
                else:
                    old_rebound = self._accumulated_rebound.get(area_id, q_rebound)
                    self._accumulated_rebound[area_id] = (old_rebound * old_dt + q_rebound * dt_minutes) / new_dt
            self._accumulated_dt[area_id] = new_dt
            self._accumulated_mode[area_id] = ekf_mode

            if self._accumulated_dt[area_id] >= EKF_UPDATE_MIN_DT:
                pf = self._accumulated_pf.pop(area_id, 1.0)
                batch_rebound = self._accumulated_rebound.pop(area_id, None)
                self._model_manager.update(
                    area_id,
                    current_temp,
                    T_outdoor,
                    ekf_mode,
                    self._accumulated_dt[area_id],
                    can_heat=can_heat,
                    can_cool=can_cool,
                    power_fraction=pf,
                    q_solar=q_solar * shading_factor,
                    q_residual=q_residual,
                    q_occupancy=q_occupancy,
                    q_rebound=batch_rebound,
                    heating_source=heating_source,
                    dehumidifier_kw=self._aux.get(area_id, 0.0),
                )
                self._accumulated_dt[area_id] = 0.0

        self.last_temps[area_id] = current_temp

    def clear(self, area_id: str) -> None:
        """Clear accumulated EKF state for a room."""
        self._sources.pop(area_id, None)
        self._aux.pop(area_id, None)
        self._accumulated_dt.pop(area_id, None)
        self._accumulated_mode.pop(area_id, None)
        self._accumulated_pf.pop(area_id, None)
        self._accumulated_rebound.pop(area_id, None)

    def remove_room(self, area_id: str) -> None:
        """Clean up all state for a removed room."""
        self.clear(area_id)
        self.last_temps.pop(area_id, None)
