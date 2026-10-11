# Fixed-GMT AC heating tariff and morning preparation

Household beta **1.7.9b5** adds an optional AC heating lockout and a configurable
morning boost. Both start disabled; installing the release does not enable them.
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
- **Temporary AC target increase: 3°C**: helps overcome the Toshiba unit's
  internal temperature reading. It is added to an existing AC Direct offset and
  clamped to the device's supported temperatures. It never changes a radiator offset.

The selected room uses its first higher heating target within six hours after the
cutoff. For example, a night target of 19°C and a 07:00 target of 21°C produces a
21°C room target during preparation. A constant schedule uses its current target.
Both Home Assistant Schedule Helpers and RoomMind reusable schedules work.
RoomMind adds no extra degrees above that scheduled room target.

During preparation, the AC is preferred for heat. Its device setpoint may be 24°C
while the independent room target is 21°C. When that room sensor reaches 21°C,
RoomMind stops the AC boost, even during a shared minimum-run hold. This is a
control target, not a guarantee against residual warmth or sensor/control delays.

After cutoff, the heating target returns to the current schedule; the upcoming
morning cooling limit remains until the morning change. This prevents the night
cooling target immediately undoing the preparation. The hold survives a RoomMind
reload. An override, absence, vacation, disabled control or disabled boost cancels
preparation. Cooling above the held morning limit remains available.

Shared bedroom cooling priority still wins when applicable. If AC heating is
unavailable or blocked by the shared outdoor unit, available radiators can supply
the target instead. This preserves comfort, but is not an all-AC energy guarantee.

This first version uses the configured lead time; it does not yet predict a room's
required warm-up time or guarantee reaching the target by the tariff cutoff.
Use the room history and the overall heat-pump CT clamp to tune lead time and
bias. Eco / High Power switches, solar and battery optimisation are not automated
in this version.

## Check the first morning

Room cards and room details show **AC heat locked (peak)**, **Morning boost**, or
**Morning warmth**. These describe the tariff policy/preparation, not proof the
compressor is physically running.

Verify that:

1. During the last off-peak minutes, the room heat target becomes its morning
   target and the AC can heat; the independent room temperature remains the reference.
2. After 05:00 GMT, the AC stops heating and a heating override uses radiators.
3. Cooling remains available during peak time and radiator cooling protection works.
4. The normal morning schedule takes over at its local scheduled time.

To disable preparation while retaining the peak lockout, turn off only
**Prepare morning targets before off-peak ends**. To restore the previous AC
heating policy, turn off **Block AC heating during peak hours**.
