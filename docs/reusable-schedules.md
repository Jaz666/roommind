# Reusable comfort schedules — beta 1.7.9b4

Open **RoomMind → Schedules**. This page stores weekly schedules in RoomMind;
you no longer need to edit Home Assistant Schedule Helpers for rooms assigned
to these schedules. Existing helpers and their room configurations are retained.
Nothing switches schedule source merely by installing this release.

## Create Living Room, Downstairs and Bedrooms

Use the named starter buttons or **New schedule**. Starters are editable drafts,
not automatic room assignments. Living Room starts at 21 / 21.5 °C, Downstairs
at 20 / 20.5 °C, and Bedrooms at 20 / 20.5 °C by day and 19 / 19.5 °C between
22:00 and 07:00. All seven days initially match. Review these suggestions before
assigning rooms; overnight downstairs optimisation is a later feature.

Choose a day, then edit **From**, **Until**, **Heat below**, and **Cool above**.
The temperatures describe comfort at the room's selected temperature sensor;
RoomMind's normal control tolerances and device offsets still apply. The cooling
target must be at least the heating target. Radiator-only rooms use heating
only, and schedules assigned entirely to heating-only rooms show one target
column. Cooling values are retained if AC rooms are assigned later.

The timeline shows heating targets. Drag a boundary in 15-minute steps, use its
left/right arrow keys, or enter a precise minute in the time fields. Moving a
boundary also moves the adjacent block, so there are no uncovered periods.
**Split** adds a block with the same targets; change its temperatures afterwards.
**Remove** extends the previous block, or the following block when removing the
first one. Each day always runs from 00:00 to 24:00.

Under **Copy this day**, tick destination days and choose **Copy to selected days**.
This replaces those days in the draft. **Duplicate** copies a complete saved
schedule into an unassigned draft with a new name.

Tick rooms under **Assign rooms** and choose **Save schedule and assignments**.
Only configured indoor rooms appear. Assignments stay linked: subsequent edits
to that schedule update every assigned room. A room follows one reusable schedule
at a time; selecting it replaces its previous assignment. The current assignment
is shown beside rooms that follow another reusable schedule.

**Cancel** discards the draft. Invalid times, gaps, overlaps, temperatures outside
5–35 °C, inverted heat/cool bands, and stale edits are rejected. An assigned
schedule cannot be deleted: uncheck all its rooms and save first. If another
window changes a schedule or its assignments, cancel and reopen it before editing.

## Import your existing helpers

Expand **Import a Home Assistant schedule helper** on the Schedules page. Choose
the helper and the heat/cool targets to use outside its active blocks, then
choose **Import as draft**. Values are converted from HA's display units. Missing
days and inactive periods are filled with the chosen targets so the entire week
is visible. Single `temperature` values are imported as matching heat and cool
targets; review these and widen the comfort range where appropriate.

Import does not modify the helper, save the new schedule, or assign rooms. Review
all days, rename the schedule if needed, tick its rooms, and save. This is useful
for replacing helper editing while retaining a familiar starting schedule.

## Room pages and overrides

Each room's Schedule card shows its linked schedule, scheduled comfort targets,
and next temperature change. Existing current-target displays continue to reflect
any override, vacation, absence or mould-prevention adjustment. Choose **Manage
reusable schedules** to edit the linked schedule centrally.

In the room's Schedule edit dialog, **Schedule source** selects a reusable
schedule or **Home Assistant helpers / constant comfort**. This source selection
saves immediately, like other room settings. Selecting helpers restores that
room's existing helper configuration; if there are no helpers, it uses the room's
constant comfort targets. Cover schedules remain separate.

Temporary overrides still take priority. Rooms following a changing reusable
schedule also offer **Until next schedule change** alongside the existing 1h,
2h and 4h options. The expiry is fixed when the override is created. Editing the
schedule afterwards does not move that expiry. A constant weekly schedule has
no next-change option.

Schedules follow HA's configured timezone, including daylight saving. For this
household use **Europe/London**. On a repeated autumn hour, targets follow the
repeated wall times; on the spring clock jump, they immediately follow the new
local time. This is separate from the household electricity tariff's fixed GMT
hours. Current targets, controller lookahead and analytics use the same weekly
blocks, stored internally in Celsius and displayed in HA's temperature units.

## Install and rollback

Install **1.7.9b4** from HACS for **Jaz666/roommind** and restart HA. See
[test-release.md](test-release.md) for backup and ZIP installation instructions.
You can create and save all three schedules without assigning any rooms first.
Keep AC devices and protection settings as they are while setting up schedules.

To stop using a reusable schedule, change the room's Schedule source back to
helpers. Before downgrading to beta 3, restore helper sources for all assigned
rooms and retain a Home Assistant backup: older code does not understand or
preserve the new schedule library when it writes storage.

## Development validation

Run `pytest -o asyncio_mode=auto tests`, the frontend build, lint, and formatter
checks. The real HA scenario `dev/sim/bin/sim run reusable-household-schedules`
checks linked targets at bedtime, reload persistence, AC cooling protection,
override expiry, and restoring comfort targets after unassignment.

After building the panel, run `dev/sim/browser/reusable_schedules.py` using a
Python environment with Playwright installed and `/usr/bin/chromium` available.
It exercises the built components at phone and desktop widths. Its HA responses
are fixtures; the separate simulator exercises the real WebSocket and control
paths. A mobile screenshot is written under `/tmp` for inspection.
