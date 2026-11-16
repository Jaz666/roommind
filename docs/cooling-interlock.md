# Heating protection during externally controlled cooling

This first household adaptation lets RoomMind supervise radiator heating while an
AC remains controlled by its own app or Home Assistant automations. It is opt-in
per room and does not change existing configurations.

## Configuration

In the room detail panel, find **Heating protection during cooling** and add that
room's AC climate entity as a monitor. Keep its independent room temperature
sensor selected as usual. The AC does **not** need to be added as a RoomMind
controlled device; a monitor gives RoomMind no authority to start or stop it.

For the initial trial, keep radiator control enabled and leave the AC out of the
controlled-device list. Removing every monitor disables protection for that room.

Defaults:

- Recovery delay: **5 minutes** after cooling is no longer selected.
- Temperature margin: **0.3°C** below the current heating target before release.

Both conditions must be met. With a 19°C heating target, recovery ends only after
the delay and a measured room temperature below 18.7°C. This margin can be reduced
in the panel for tighter comfort control; it does not lower the room's target.
The margin applies after cooling/unknown status, not to normal heating beforehand.

WebSocket configuration fields on `roommind/rooms/save`:

```json
{
  "type": "roommind/rooms/save",
  "area_id": "YOUR_EXISTING_ROOM_AREA_ID",
  "cooling_interlock_entities": ["climate.bedroom_ac"],
  "cooling_interlock_delay": 300,
  "cooling_interlock_deadband": 0.3
}
```

Delay uses seconds (0–3600); the temperature margin uses Celsius (0–2). Saved
recovery state survives integration reloads and Home Assistant restarts.

## Behaviour

- Selected **cool** or **dry** mode blocks heating even when the AC is temporarily
  idle. An observed cooling/drying action also blocks it. The Toshiba integration
  reports selected mode, not actual compressor operation, so mode is the signal.
- Missing/unavailable AC status, or automatic mode without observed cooling,
  blocks heating conservatively. Select an explicit mode to resolve automatic-mode
  ambiguity. A return to known non-cooling status starts recovery.
- Protected radiators receive the existing off/minimum-setpoint fallback. Normal
  setback idle policies, valve-protection cycling, and minimum-run holds cannot
  reopen them through RoomMind while protection is active.
- Other rooms continue requesting heat normally. A radiator-room boiler master
  receives no heating demand from a blocked room.
- Learned thermal parameters and observation counts pause. The temperature state
  still follows the room sensor, so the entire external cooling drop is not learned
  as heat loss when training resumes. Short-term predictions are suppressed during
  protection. The main temperature history remains available.
- The panel reports cooling, recovery, or unknown cooling status as the reason.
- Global or per-room control disabled means RoomMind sends no commands, including
  interlock commands. Protection requires active RoomMind radiator control.

Home Assistant state-change events request a coordinator refresh, and the normal
30-second loop also checks the monitors. This is not an instantaneous physical
interlock: Toshiba/cloud reporting delays and failed TRV commands can delay actual
closure. The status represents RoomMind's control decision, not verified valve
position. Tado app changes/schedules can still compete with it until the next
refresh. Avoid having multiple independent automations repeatedly write the same
radiator setpoint.

## Validation and initial trial

Automated coverage includes externally requested cooling, selected cooling with
an idle compressor, unknown/automatic modes, sensor startup, delay and temperature
release, persisted recovery, learning preservation, valve cycling, and unrelated
rooms continuing to heat. The real-HA simulator scenario is:

```bash
ROOMMIND_SIM_HOME=/workspace/roommind-sim dev/sim/bin/sim run external-cooling-interlock
```

It deliberately requests cooling below the heating target to prove that the
interlock wins over genuine radiator demand; it is not a comfort/efficiency test.

Before a live trial, build the frontend with `cd frontend && npm ci && npm run
build` and package it with the integration. No live household settings are changed
by development or simulator commands. Trial one room, watch Tado heating demand
and radiator temperature during cooling, then verify recovery. Remove its monitor
to revert this feature; existing room/device configuration stays intact.

## Following stages

Beta 3 adds opt-in [shared Toshiba outdoor-unit mode arbitration](shared-ac-control.md).
The standalone cooling-interlock feature does not provide
tariff selection, morning recovery/preheating, or background radiator flow.
Tariff and background-flow changes remain separate from the shared-unit trial. A Sonoff closing-degree limit manually reduced below full
closure can permit background flow even with the thermostat off; this first stage
does not write those number entities.
