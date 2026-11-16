# Household fork update — 1.8.0b1

This prerelease integrates upstream RoomMind main through commit
`be759ec4ca23a4317e6d1c6dc29fb07a2a3f03b1` (version 1.8.0), retaining the household
fork's reusable schedules, shared Toshiba direction control, radiator cooling
protection, fixed-GMT tariff and revised morning preparation.

## Upgrade

Back up Home Assistant before upgrading. In HACS, keep tracking **Jaz666/roommind**,
select prerelease **1.8.0b1**, install and restart HA. Keep the configured RoomMind
integration and its rooms. The release's `roommind.zip` includes the built panel;
GitHub's automatic source ZIP does not. See [installation and rollback](test-release.md).

Check room sensors, reusable schedule links, the complete Toshiba compressor
group, tariff times **00:00–05:00 GMT/UTC**, selected boost rooms and the early-stop
margin after installation. Cooling remains allowed at peak rates. This update
adds no off-peak gas lockout or new AC-first policy: those remain a later decision.

## Changes relevant to this household

- **Direct valve control:** recognised Sonoff TRVZB opening/closing number entities
  can be enabled in a device's settings. This is opt-in. It will replace manually
  adjusted degree settings while RoomMind controls the valve; record your useful
  calibration values before enabling it. Advertised opening percentage is not a
  calibrated water-flow measurement. Tado still has no writable opening control.
- **Cooling protection with direct valves:** the fork explicitly commands zero
  opening during cooling/recovery, as `climate.off` alone cannot close a valve held
  open through its degree settings. This bypasses the normal valve dwell time.
- **AC calibration:** upstream can learn internal-sensor offsets for proportional
  AC control when useful temperature and `hvac_action` data are available. It does
  not replace explicit Direct offsets. The Toshiba integration inspected during
  this update does not implement `hvac_action`, so do not assume automatic learning
  works with those entities. Existing Direct calibration remains applicable.
- **Heat only:** in rooms containing both radiators and ACs, upstream now leaves
  AC heating out unless heat-source orchestration is explicitly enabled with an
  external sensor. Use **Auto** for rooms intended to heat and cool with Toshiba,
  as in [the shared-unit guide](shared-ac-control.md). Shared planning honours this
  exclusion so a radiator-only room cannot block other rooms' AC direction.
- **Room climate entities:** upstream supplies a native climate entity per room,
  including Schedule/Manual presets. Legacy per-room controls are deprecated,
  rather than immediately removed. Review HA repair notices and migrate affected
  automations when convenient. Your Tado/Toshiba device entities stay in use.
- **Occupancy eco:** an optional room-vacancy setback is available. It stays
  disabled unless configured; review comfort implications before using it.
- **Mould estimates:** wall-insulation assumptions are configurable, and estimated
  surface temperature is exposed. These remain estimates. Automatic prevention
  is still separate from notification thresholds; this does not introduce the
  per-room humidity strategies discussed for Bedroom Two and the Living Room.
- **Controller fixes:** upstream improves minimum-run continuation, restart state,
  advance heating/cooling, cooling-only overrides and analytics predictions.

Direct valve control does not yet implement the proposed boiler-return feedback
or recruitment of supporting radiators. Overnight heat-source priorities remain
as documented in [the tariff guide](heating-tariff.md).

## First checks

1. Confirm reusable schedules and their room assignments are present.
2. Check a normal heating request, then a cooling request in one bedroom: its
   radiator must be inhibited and shared Toshiba direction changes must wait.
3. Observe the next cheap-rate period and morning handover. Keep the 0.2°C early
   stopping margin initially unless you have already tuned it.
4. Trial direct Sonoff control separately after recording existing manual degree
   settings; do not combine that experiment with the first overnight upgrade check.

## Rollback

Keep a backup of the integration directory and HA configuration from before this
upgrade. New upstream room climate entities and features are absent in beta 6;
restore any automations changed to depend on them if rolling back. Disable direct
valve control while this version is still running before a downgrade, so it can
hand back valve ownership. Preserve notes of manual Sonoff settings: normal
hand-back restores the device degree limits rather than your earlier calibration.
