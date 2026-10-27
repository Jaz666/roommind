# Household heating and source-aware learning — 1.8.0b2

## Heating rules

With the AC tariff enabled, Heat Only rooms may use their ACs throughout the configured cheap period (00:00–05:00 GMT by default), even without heat-source orchestration. In mixed radiator/AC Heat Only rooms, cheap-rate heating prefers an available AC above its configured minimum outdoor temperature; radiators remain the fallback. AC-only rooms retain AC heating. Auto rooms keep their normal source selection outside the explicit morning boost.

At peak rate, AC heating is blocked. Radiators may still heat, and an AC configured to idle in Fan Only keeps its selected fan speed. The block overrides compressor minimum-run holds. Heat Only does not permit cooling. Auto still permits cooling, with the shared-outdoor-unit direction and radiator cooling protections unchanged.

Morning boost is separate: in its configured preparation window it uses the upcoming scheduled heating target, without the old extra +3°C bias, and retains the existing stop margin and cooling handover band.

## Learning and migration

Each room now shares one set of heat-loss, solar and occupancy parameters but learns independent radiator and AC heating strengths. The model also learns a separate temperature-response coefficient for measured dehumidifier electrical kW. Electrical watts are an input regressor, not an assumed measurement of delivered heat or COP.

Mixed-source models migrate once: shared room properties and cooling learning are retained, but their previously combined heating estimate and heating sample counts are replaced with fresh source estimates. Single-source learning is preserved. Each source needs its own heating observations before predictive heating can use it. Analytics shows separate radiator/AC strengths; a dash means insufficient source observations. The general confidence score is a room-level summary, not a guarantee about an untrained source.

Temperature observations are labelled using device states captured **before** new control commands. Clean source changes discard the crossing batch. Simultaneous radiator and AC operation, conflicting modes, unavailable configured power readings, or unobservable operation cannot train either heating coefficient; temperature is synchronised so the skipped interval does not contaminate the next sample.

Changing the selected temperature sensor through RoomMind resets only that room's thermal learning and clears its accumulated training. Moving or replacing a physical sensor while keeping the same entity ID still requires a manual reset.

### Limits of the first version

- Tado's reported heating action is evidence of its heating demand, not independent proof that the boiler burner is firing or a measurement of radiator output.
- Toshiba without `hvac_action` requires both selected Heat mode and supporting electrical evidence. The CT cannot identify which indoor unit received heat by itself.
- Irregular Wh readings provide averaged evidence. Counter decreases, mode changes and gaps over 30 minutes discard an interval. Positive evidence expires after five minutes; flat totals never prove idle. Observed Fan Only energy rates establish a per-unit baseline where available.
- The CT is never split equally between rooms. Set its activity threshold above measured whole-system Fan Only consumption; defrost and compressor cycling can leave learning uncertain.
- When both heating sources are selected together, control conservatively uses normal on/off hysteresis rather than assuming a combined predictive model is ready. Clean single-source intervals can still train each response.
- This is still a single-temperature room model. It separates heating strengths, not full independent radiator/AC warm-up or transport-delay models. Existing residual-heat and AC cooling-rebound handling remains approximate when sources change.
- Forecasts assume the current auxiliary power continues; they do not predict the dehumidifier's future humidistat cycles.

## Preventing all-night preheating

Room → Sensors → **Maximum predictive preheating (minutes)** defaults to 60 for fast heating systems (radiators/AC) and 720 for underfloor heating. Set it to 0 to disable schedule anticipation. The comfort/efficiency slider can shorten this maximum. The limit also bounds the predictive guard/lead targets, so an implausibly weak learned heater cannot send tomorrow's comfort setpoint all night. The same limit is used in analytics forecasts.

The separate, explicitly configured morning boost can still advance the target in its own preparation window. Current scheduled heating demand is unaffected.

## Connect this household's sensors

After installing and restarting Home Assistant, refresh the RoomMind browser panel.

1. Settings → Sensors & data sources: select **Whole heat pump power sensor (W)** = `sensor.heat_pump_consumption_power`. Start with the default 150 W activity threshold, then compare it with the CT reading while all units are in Fan Only and adjust if necessary.
2. In each room's Devices editor, expand its AC and select **AC energy sensor (Wh or kWh)**:

   | AC | Energy sensor |
   | --- | --- |
   | `climate.ac_living_room` | `sensor.ac_living_room_power_consumption` |
   | `climate.ac_master_bedroom` | `sensor.ac_master_bedroom_power_consumption` |
   | `climate.ac_alex` | `sensor.ac_alex_power_consumption` |
   | `climate.ac_amber` | `sensor.ac_amber_power_consumption` |

3. Living Room → Sensors: set **Dehumidifier power sensor** to `sensor.living_room_dehumidifier_current_consumption`. Its virtual humidistat and switch remain independently controlled. An unavailable configured reading pauses thermal learning; it does not switch humidity control or room heating off.
4. Keep AC idle action **Fan Only** and choose the desired speed, including Quiet where supported.
5. Keep the tariff enabled and rooms in Heat Only if automatic cooling is unwanted. Start with the 60-minute predictive maximum and the existing 30-minute morning boost.

Entity IDs are configuration, not hardcoded into the integration. These settings are not applied to a live Home Assistant instance by building or installing the release.

## Check after installation

- At cheap rate, request heat below the room's measured temperature only if testing idle; request a higher target to test AC heating. Verify the AC selects Heat and the radiator is parked.
- At peak, request heating: the radiator should heat, the AC should remain Fan Only, and the room should report the peak AC heating lock.
- In Heat Only, a low override must not start cooling.
- During the overnight setback, a morning target more than the configured predictive maximum away must not keep Tado at that future target plus its offset.
- Confirm the dehumidifier's W reading is available and watch separate source sample counts grow over clean heating periods. An AC strength remaining unlearned can mean insufficient energy evidence; it is not proof of a broken heater.

Rollback: install 1.8.0b1 and restart HA. Its reader can load the preserved legacy state layout, but cannot use the new source coefficients. Restore a pre-upgrade HA backup for an exact restoration of earlier learning and settings.
