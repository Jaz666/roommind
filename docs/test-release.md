# Household beta installation and rollback — 1.7.9b5

This experimental prerelease adds a fixed-GMT AC heating tariff and bounded
morning preparation, retaining reusable schedules and shared Toshiba control.
Enable the new features in Settings after installation; both start disabled.
Follow [the tariff guide](heating-tariff.md), and use
[reusable schedules](reusable-schedules.md) to define morning room targets.

Before installing, make a Home Assistant backup and download it. Also preserve
an exact copy of `/config/custom_components/roommind` outside `custom_components`
if your configuration-file access allows it. Record your installed version.
Declared minimum HA version is 2026.5.0; simulator validation uses 2026.10.0.

## Install

Use HACS tracking **Jaz666/roommind**, select prerelease **1.7.9b5**, install it,
and restart Home Assistant. Keep one RoomMind repository in HACS: an upstream
update can overwrite the fork. Do not delete the configured RoomMind integration;
the domain is still `roommind`, preserving rooms and settings.

Alternatively, extract the verified release asset `roommind.zip`, replacing
`/config/custom_components/roommind` with its contents. The ZIP root contains
`manifest.json` and `frontend/roommind-panel.js`. GitHub's automatic source ZIP
is not an installation asset because it lacks the generated panel. Restart HA.

The panel URL includes the version to refresh its code after upgrades. If the
normal browser still shows an older panel, try a private window or hard refresh.
Check your rooms, schedules and sensor selections before enabling new control.

## Set up schedules first

Open **RoomMind → Schedules**, create or import Living Room, Downstairs and
Bedrooms, review their weekly blocks, then assign rooms. You can save all three
without room assignments first. See [the schedule guide](reusable-schedules.md).
Keep the current AC device configuration while doing this.

## Resume AC trials later

- To continue radiator-only protection while Toshiba is independently controlled,
  keep the AC out of controlled Devices and follow [cooling protection](cooling-interlock.md).
- To return your bedroom Toshiba to RoomMind control, follow
  [shared Toshiba setup and trial](shared-ac-control.md). Configure the full
  outdoor-unit group first, but give RoomMind control of your bedroom AC only
  for the first live trial. Keep the other ACs off initially.

## Roll back

Before returning to beta 3 or earlier, restore **Home Assistant helpers / constant
comfort** as the Schedule source in every room. Preserve a HA backup containing
the new schedule library: older versions do not preserve it when writing storage.

Stop Toshiba cooling first. Remove ACs from controlled Devices before returning
to beta 2, which does not coordinate shared requested modes. Keep Tado devices,
external sensors and independent cooling monitors as appropriate.

Restore the exact code/panel directory saved before installation and restart HA,
or reinstall your previous fork release through HACS. Restore the HA backup if
configuration needs reversing too. Avoid unrelated household changes during the
trial so a full backup restore does not discard them.

## Building a release

A release tag must point to the tested source commit, with the same version in
`const.py` and `manifest.json`. Publish as a prerelease. GitHub Actions' **Release**
workflow checks out the tag, builds the frontend and attaches `roommind.zip`.
Wait for that workflow to succeed and verify the asset before installing through
HACS. This avoids the cloud environment's direct-upload authentication failure.
