# Household cooling-interlock trial: 1.7.9b1

This is an experimental prerelease of the household fork. It adds opt-in radiator
heating protection for independently controlled AC units. Shared Toshiba mode
arbitration and tariff-based heating are not included yet.

## Before installing

1. Check the Home Assistant version. The repository declares **2026.5.0 or later**
   as its minimum supported version. The package was tested in HA 2026.10.0.
2. Record the currently installed RoomMind version.
3. Make a Home Assistant backup, and download it to another machine. Also copy
   the existing `/config/custom_components/roommind` directory somewhere outside
   `custom_components` if you have access to the configuration files. This copy
   preserves your exact installed code and panel for rollback.
4. Keep the Toshiba units out of RoomMind's controlled-device lists. Keep each
   room's current Tado devices and independent temperature sensor unchanged.

The integration domain remains `roommind`: replace the existing integration,
do not try to install a second copy alongside it.

## Install the test package manually

Use the verified `roommind.zip` asset for **1.7.9b1**. It contains `manifest.json`,
Python modules, and `frontend/roommind-panel.js` at its root; it does not contain
an enclosing `custom_components` directory.

1. Extract the ZIP to a temporary directory on your own machine and confirm the
   manifest version is `1.7.9b1`.
2. Replace `/config/custom_components/roommind` with the extracted directory's
   contents, using your existing configuration-file access (SSH/Samba/Studio Code
   Server, for example). Keep the backup outside `custom_components`.
3. Restart Home Assistant. A full restart ensures the new Python code is loaded.
4. Reload the RoomMind browser panel. If it displays a version mismatch, refresh
   its cache and verify that the new JavaScript bundle was installed.
5. Confirm your existing rooms, schedules, and sensors remain present before
   enabling the new feature. Leave the other three rooms' monitor lists empty.

If your existing HACS entry tracks upstream, it can overwrite a manually installed
beta on its next update. Avoid an upstream update during the trial. Switching
HACS permanently to `Jaz666/roommind` is a separate step after a successful trial.

## Enable protection in your bedroom only

Open the existing Bedroom One/master-bedroom room in RoomMind. The mapping is:

| Role | Home Assistant entity |
| --- | --- |
| Cooling monitor | `climate.ac_master_bedroom` |
| Existing radiator control | `climate.tado_master_bedroom` |
| Existing room temperature | `sensor.mum_dad_temperature` |
| Demand feedback to observe | `sensor.mum_dad_heating_power` |

Under **Heating protection during cooling**, add `climate.ac_master_bedroom` as a
monitor. Do not add it to the controlled devices. Leave Full Control enabled for
the room's radiator.

The initial recovery delay is five minutes. The default recovery margin is 0.3°C;
use **0.1°C** for the initial household trial, given your sensitivity to temperature
swings. The margin only gates radiator heating after cooling has stopped: with a
19°C heating target, a 0.1°C margin requires a reading **below 18.9°C**, and the
five-minute delay must also have passed. It does not request cooling to 18.9°C or
change your normal 19°C target. Do not deliberately cool below your comfort range
just to force heating to resume.

## Observe one normal bedtime cooling period

1. Note the external room temperature, RoomMind heating target, and Tado demand.
2. Start cooling through the Toshiba app as you normally would. Use explicit
   **Cool**, rather than **Auto**, for this trial.
3. Confirm Home Assistant reports `climate.ac_master_bedroom` in `cool` mode.
4. Confirm RoomMind reports **Heating blocked: cooling mode selected** and the
   Tado heating target/mode is lowered/off. Watch demand fall and the radiator stop
   receiving new heat. Warm metal can remain warm after the valve closes.
5. Verify the Toshiba stays running and other rooms can still request heat.
6. Stop cooling normally. Observe the recovery message. Heating is eligible again
   only after the delay and temperature margin; normal room demand then decides
   whether to heat.

Toshiba reporting, the coordinator refresh, Tado reporting, and the physical valve
all have delays. The feature is a software control policy, not an instantaneous
physical guarantee. If demand remains sustained while cooling, or your comfort
deteriorates, stop the trial rather than tightening settings blindly. An unavailable
AC or ambiguous Auto mode deliberately blocks heating until status is resolved.

Record timings, external temperatures, Tado demand, and any relevant Home Assistant
log messages. That evidence will guide tuning before enabling the other rooms.

## Disable or roll back

For a configuration rollback, stop AC cooling first, then remove the monitor from
the room's **Heating protection during cooling** list. RoomMind returns to its
previous radiator-control behaviour; the AC remains independently controlled.

For a code rollback, restore the exact integration directory saved before the
trial, restart Home Assistant, and reload the panel. If configuration was also
changed unexpectedly, restore the Home Assistant backup. Avoid making other
household changes during the trial so a full backup restore does not discard them.

## Publish through GitHub when API access is available

The test code belongs on branch `household/cooling-interlock`. In GitHub Releases,
create a release targeting that branch's tested commit, with tag `v1.7.9b1` and
**Set as a pre-release** selected. Attach `roommind.zip`; keep it off the latest
stable release channel. The repository release workflow can also build and upload
that asset when publishing triggers it. Check that the asset is present before
attempting an installation.

The environment needs `api.github.com` for release creation and
`uploads.github.com` for uploading the asset. Existing Git-proxy access does not
by itself prove GitHub API or write permission.
