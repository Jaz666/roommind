# Fixed-GMT AC heating tariff and morning preparation

Household beta **1.7.9b6** revises morning preparation to reduce overshoot and
heating/cooling reversals. It retains an optional AC heating lockout and a configurable
morning boost. New installations start with both disabled. Upgrades retain your existing
enabled features and room selections.
The reusable schedule editor and cooling protection remain available.

## Enable the peak heating lockout

Open **RoomMind → Settings → Electricity tariff and morning boost** and enable
**Block AC heating during peak hours**. Keep the off-peak times at **00:00** and
**05:00 GMT / UTC**. Settings save automatically.

These times never move with daylight saving: in winter the window is 00:00–05:00
local time; during BST it is 01:00–06:00. Room schedules still use Home Assistant's
local timezone, so a 07:00 morning schedule stays at 07:00 local time.

During peak hours, RoomMind sends heating demand to available radiators and
prevents AC heating, including heating overrides and AC idle setback. Cooling
remains available for comfort and still blocks radiator heating in the room being
cooled. AC-only rooms cannot heat during peak hours. Existing radiator Direct
setpoint offsets, including your Living Room +0.5°C, are preserved.

At the first control update after the cutoff, heating ACs are turned off even if
their shared group would otherwise finish a minimum run. Auto / heat-cool mode is
also stopped because it could heat; RoomMind selects explicit modes for normal
control. Shared direction changes and minimum off time still apply. Disabled
RoomMind control leaves devices untouched: this is a RoomMind command policy,
not a lock against commands from the Toshiba app or other automations.

## Enable morning preparation

Enable **Prepare morning targets before off-peak ends**, then select the rooms
you want to prepare. Rooms must have an AC and an independent temperature sensor.
Start with the **Through Lounge / Living Room**; rooms without ACs cannot use this
feature. Keep the shared Toshiba outdoor-unit group configured with all four ACs.

Initial settings:

- **30 minutes before cutoff**: starts at 04:30 GMT, or 05:30 BST.
- **Stop heating 0.2°C below the morning target**: allows residual warmth to
  carry the room towards comfort. The setting accepts 0–1°C. Heating resumes only
  if the room falls another 0.3°C below this stopping point.

The selected room uses its first higher scheduled heating target within six hours
of the cutoff, or its current scheduled target if constant. A night target of 19°C
and a 07:00 target of 21°C therefore produces a 21°C preparation target. Both HA
Schedule Helpers and reusable schedules work. Morning preparation does not add
mould-prevention increases to that target; ordinary mould prevention resumes
outside the preparation window if enabled.

**The beta 5 temporary AC target increase has been removed.** Existing saved
`ac_morning_boost_offset` values are ignored. During preparation, AC heating uses
the room's morning target plus any existing Direct device calibration offset,
subject to the device's limits and temperature-step rounding. It does not use an
additional morning offset or the proportional maximum-temperature boost.

With a 21°C morning target and the default 0.2°C stopping margin, RoomMind stops
heating at 20.8°C, even during a shared minimum-run hold. The stopping decision
survives reload and hysteresis prevents restarting immediately after a small
sensor fluctuation. A missing fresh room reading pauses preparation heating.
This is a control threshold, not a physical guarantee against thermal inertia or
sensor/control delays. Increase the margin modestly if measured overshoot persists.

After cutoff, heating returns to the current schedule. Cooling retains the higher
of the normal limit, the prepared morning cooling limit, and the morning heating
target plus 0.5°C. This handover lasts until the morning schedule change or 30
minutes after cutoff, whichever is later. Constant schedules and schedules that
change exactly at cutoff also receive the 30-minute handover. It survives reload.
For example, equal 20°C heat/cool targets temporarily become 20°C / 20.5°C, allowing
small residual warmth to dissipate naturally before normal cooling resumes.

Cooling above that held limit remains available. Explicit overrides cancel the
handover immediately; shared outdoor-unit changeover/off timers still apply to
device commands. Absence, vacation, disabled control or disabled preparation also
cancel the hold. No new handover is applied to a room that did not prepare.

Shared bedroom cooling priority still wins when applicable. If AC heating is
unavailable or blocked by the shared outdoor unit, available radiators can supply
the target instead. This preserves comfort, but is not an all-AC energy guarantee.

Preparation uses the configured lead time; it does not yet predict a room's
required warm-up time or guarantee reaching the target by the tariff cutoff.
Use the room history and the overall heat-pump CT clamp to tune lead time and
stopping margin. Removing the extra AC bias may slow recovery for units with
inaccurate internal thermostats; review ordinary device calibration and allow
more lead time as needed. Eco / High Power switches, solar and battery optimisation are not automated
in this version.

## Check the first morning

Room cards and room details show **AC heat locked (peak)**, **Morning boost**, or
**Morning warmth**. These describe the tariff policy/preparation, not proof the
compressor is physically running.

Verify that:

1. During the last off-peak minutes, the room heat target becomes its morning
   target and the AC can heat; the independent room temperature remains the reference.
2. Heating stops at the configured margin below the target and stays off through
   small temperature fluctuations. After 05:00 GMT, AC heating is locked and a
   heating override uses radiators.
3. Cooling remains available during peak time and radiator cooling protection works.
4. The normal morning schedule takes over at its local scheduled time.

To disable preparation while retaining the peak lockout, turn off only
**Prepare morning targets before off-peak ends**. To restore the previous AC
heating policy, turn off **Block AC heating during peak hours**.
