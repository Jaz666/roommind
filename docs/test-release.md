# Personal release 2.2.0 — installation and rollback

This personal release updates the cooling-interlock fork to upstream RoomMind 2.0 and keeps the household-specific controls. It includes room heating protection while an AC is cooling, tariff-based AC heating lockout and AC Morning Boost, shared Toshiba outdoor-unit coordination, and source-aware learning for ACs and the Living Room dehumidifier. The custom scheduler and custom predictive-preheat limit have been removed; Home Assistant schedules and RoomMind's standard predictive preheat remain.

Read the setup notes for [cooling interlock](cooling-interlock.md), [tariff controls](heating-tariff.md), [shared AC control](shared-ac-control.md), and [source-aware learning](source-aware-learning.md). Configure the sensors and tariff settings explicitly; installing this release does not select entities or change the boiler's manually configured maximum flow temperature.

## Install

1. Make a Home Assistant backup and download it. Record your current version.
2. In HACS, keep **Jaz666/roommind** as the RoomMind repository. Select **2.2.0**, install, and restart HA. Do not delete the configured integration.
3. Refresh the RoomMind panel. If the old frontend persists, use a hard refresh or private window.
4. Follow [sensor setup](source-aware-learning.md#connect-this-households-sensors): whole-system CT, per-AC energy counters, and Living Room dehumidifier power. Installing the release does not silently configure these entities.
5. Check the new cooling-interlock AC list, tariff hours and shared-compressor settings before relying on those controls.

Alternatively, replace `/config/custom_components/roommind` with the contents of the release's **roommind.zip** and restart HA. The ZIP root contains `manifest.json` and `frontend/roommind-panel.js`. GitHub's automatic source ZIP lacks the generated panel and is not the installation asset.

Declared minimum HA version is 2026.5.0. Simulator validation uses HA 2026.10.0.

## Roll back

Reinstall the previous release in HACS (or restore its integration directory) and restart HA. Reusable schedule assignments and the household-specific settings are kept in RoomMind storage and may be ignored by older releases; restore your pre-upgrade HA backup if you need the exact previous configuration.

## Build a release

The release tag must point to the validated commit and match `const.py` and `manifest.json`. GitHub Actions' **Release** workflow builds the frontend and attaches **roommind.zip**. Verify the asset is present before installing through HACS.
