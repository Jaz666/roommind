# Household shared Toshiba control — beta 1.7.9b3

This adds opt-in coordination for indoor units sharing one outdoor unit. It
selects a direction before any room commands are issued. Existing installations
remain unchanged until **Coordinate shared AC direction** is enabled for a group.

## Direction policy

- When heating and cooling conflict, heating normally wins.
- From **22:00 to 07:00 in Home Assistant local time**, a cooling request from a
  selected bedroom unit takes priority. This follows GMT/BST changes; it is
  separate from the electricity tariff, which stays on GMT.
- Only units with their own room demand start. An idle bedroom is not cooled
  merely because another bedroom needs cooling.
- A room wanting heat can use its available radiators while its AC is blocked.
  This also works when its heat-source selector would normally prefer the AC.
- Radiators in a room requesting or reporting cooling are protected automatically.
  The existing recovery delay and temperature margin still apply. An explicit
  monitor list lets you edit those settings in the room panel.

The group retains an existing direction through its minimum run time. For a
changeover it stops that direction, waits for Home Assistant to report the units
in Off/Fan mode, and then observes the minimum off time before starting the other
direction. A new start has a 90-second allowance for delayed cloud state reports.
Changeover timestamps persist across integration reloads and HA restarts.

These are selected-mode timings, not verified compressor operation. Toshiba
thermostats and hardware protections still apply; the CT clamp is not used yet.
An unavailable or ambiguous Auto/Heat-Cool member prevents a new group direction.
A unit outside RoomMind control is never commanded: its reported active direction
constrains the group until it stops. Do not keep competing app schedules or
Home Assistant automations writing to units you give RoomMind control over.

RoomMind-controlled cooling continues thermal learning. Independently controlled
cooling and recovery pause learning. Compressor-based coil drying is replaced by
fan-only drying for these controlled ACs, so drying cannot start a conflicting
cooling direction behind the group's decision.

## Configure the Toshiba group

Back up Home Assistant before installing or changing control ownership. Install
**1.7.9b3** and restart HA. Verify **Settings → System → General → Time zone** is
**Europe/London**.

Stop all four Toshiba units before initial setup. In **RoomMind → Settings →
Compressor Protection**, add or edit one group named `Toshiba` with all four ACs:

| Room | Group member | Bedroom priority |
| --- | --- | --- |
| Through Lounge | `climate.ac_living_room` | No |
| Bedroom One | `climate.ac_master_bedroom` | Yes |
| Bedroom Three | `climate.ac_alex` | Yes |
| Bedroom Two | `climate.ac_amber` | Yes |

Enable **Coordinate shared AC direction** and tick the three bedrooms under
**Bedroom cooling priority**. Use **5 minutes minimum run** and **5 minutes
minimum off** for the first trial. The usual new-group default is 15 minutes run;
change it deliberately if using the five-minute trial setting. Enabling shared
control clears the legacy master/script/uniform-mode settings because those are
an alternative control path.

Settings save automatically; wait for the saved indicator before leaving. Configuration
checks reject members in more than one group and bedroom priorities outside the
group. Include every indoor unit sharing the outdoor unit, even if only one is
under RoomMind control initially.

## First live trial: your bedroom only

Keep the other three Toshiba units **off and outside their RoomMind controlled
Devices lists**. Keep every existing Tado device and external sensor unchanged.

In Bedroom One:

1. Add `climate.ac_master_bedroom` to **Devices** as a **Climate Device / AC**.
2. Keep `climate.tado_master_bedroom` as a thermostat and
   `sensor.mum_dad_temperature` as the independent room sensor.
3. Keep Full Control enabled. Select RoomMind's **Auto** climate mode to allow it
   to choose heating or cooling. This is RoomMind Auto: the Toshiba receives
   explicit Heat/Cool commands, never Toshiba Auto from this control path.
4. Keep your cooling monitor and the tested **5-minute / 0.1°C** recovery settings.
5. Start with the AC's **Direct** setpoint mode. Keep the Tado's current mode and
   offsets unchanged. Toshiba's sensor bias may require a separate AC offset;
   record both temperatures before tuning it.
6. Use your normal comfortable cooling target, or a short RoomMind cooling
   override if needed. Do not force an uncomfortable temperature for testing.

A selected group direction does not overcome RoomMind's other room constraints:
open windows, unavailable sensors, disabled control, schedules and outdoor gates
still apply. The existing default blocks cooling below **16°C outdoors** unless
an override bypasses it. Check your Toshiba model's operating range before
changing the outdoor limit; this release does not change it automatically.

Observe explicit `cool` in `climate.ac_master_bedroom`, **Cooling protection** for
radiators, Tado demand falling, and the other ACs staying off. When cooling ends,
observe radiator recovery as in beta 2. **AC waiting** means another direction,
changeover/minimum timing or uncertain status is holding back the AC. Its tooltip
explains the categories. Do not shorten timers repeatedly to force a start.

If the unit idles before the external sensor reaches the target, record its
reported indoor temperature, target and external room temperature. That is the
next setpoint-bias test; it is distinct from direction coordination.

## Expand after the bedroom trial

Add each remaining AC to its existing room, retaining these mappings:

| Room | Tado climate | Independent room sensor |
| --- | --- | --- |
| Through Lounge | `climate.tado_living_room` | `sensor.living_room_air_quality_monitor_temperature` |
| Bedroom Three | `climate.alex_s_room_tado_alex` | `sensor.alex_s_room_tado_alex_temperature` |
| Bedroom Two | `climate.tado_amber` | `sensor.amber_temperature` |

Keep the living-room Tado on **Direct with +0.5°C**, as tested. Add each room's own
AC as a cooling monitor to expose recovery settings; start with the same narrow
margin if appropriate for that room. Enable the room's existing heat-source
selection when both Tado and Toshiba provide heating. It uses outdoor temperature
and temperature gap, not your tariffs yet. Shared cooling overrides its AC
heating preference and allows gas fallback.

Use one ordinary evening where a bedroom needs cooling and downstairs genuinely
needs heat. Confirm the bedroom AC cools, the living AC stays off, and living-room
Tado demand returns. No conflict should require changing the room temperature
targets to uncomfortable values. Other bedrooms without demand remain off.

## Stop or roll back

Stop Toshiba cooling first. Remove its AC from the room's controlled Devices list
before disabling shared coordination; leave the radiator and room sensor present.
Then disable the group's shared control. Keep an independent cooling monitor if
that room's Toshiba will be operated manually again. Removing a monitor alone
does not disable the automatic radiator protection while shared AC control owns
that unit.

For a code rollback restore your saved integration directory and restart HA, or
reinstall beta 2 while all ACs are removed from controlled Devices. Restore the HA
backup if configuration changes need reversal. No live household settings are
changed by development or simulator tests.

## Scope and validation

This release coordinates requested modes and uses RoomMind's existing temperature
controller. It does not measure per-unit power, verify valve position, infer Auto
operation, optimise tariffs/morning preheating, manage Eco/High Power modes, or
provide background radiator flow. Those remain following stages.

`dev/sim/bin/sim run household-shared-ac` uses four indoor units and Europe/London
summer time. It checks daytime priority, 22:00 bedroom priority, reported-off
changeover across a reload, gas fallback, radiator protection, inactive units,
unavailable status and recovery, with a no-simultaneous-heating-and-cooling
invariant over the entire run. Its exaggerated temperatures are policy stress
tests, not household comfort targets.
