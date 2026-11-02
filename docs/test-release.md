# Household beta installation and rollback — 1.8.0b4

This prerelease fixes Minimum Heat on Toshiba by sending a separate mode command after setting the low target. It includes the **Off / Minimum Heat** policy for idle shared-AC units while another room needs AC heat. Configure it under **Settings → Compressor groups**; see [the shared AC guide](shared-ac-control.md#toshiba-idle-units-during-ac-heating-180b3). Source-aware learning and the cheap-rate controls from 1.8.0b2 are retained. Existing schedules, tariff settings and the shared Toshiba group are retained.

Read [the source-aware learning and setup guide](source-aware-learning.md), including its migration and measurement limitations. Upgrading from 1.8.0b2 retains existing learning. If upgrading from an older release, the source-aware learning migration described in that guide still applies.

## Install

1. Make a Home Assistant backup and download it. Record your current version.
2. In HACS, keep **Jaz666/roommind** as the one RoomMind repository. Select prerelease **1.8.0b4**, install, and restart HA. Do not delete the configured integration.
3. Refresh the RoomMind panel. If the old frontend persists, use a hard refresh or private window.
4. Follow [sensor setup](source-aware-learning.md#connect-this-households-sensors): whole-system CT, per-AC energy counters, and Living Room dehumidifier power. Installing the release does not silently configure these entities.
5. Check each room's maximum predictive preheat time, AC idle action/fan speed, and Heat Only/Auto mode before the next cheap period.

Alternatively, replace `/config/custom_components/roommind` with the contents of the release's **roommind.zip** and restart HA. The ZIP root contains `manifest.json` and `frontend/roommind-panel.js`. GitHub's automatic source ZIP lacks the generated panel and is not the installation asset.

Declared minimum HA version is 2026.5.0. Simulator validation uses HA 2026.10.0.

## Roll back

Reinstall 1.8.0b2 in HACS (or restore its integration directory) and restart HA. That version retains source-aware learning but does not apply the new idle-unit policy, so Fan Only peers may block Toshiba heating again. Restore your pre-upgrade HA backup if you need the exact earlier configuration.

For much older releases, consult [the upstream 1.8 upgrade guide](upstream-1.8-update.md). In particular, beta 5 can resume its old +3°C morning bias, and beta 3 or earlier cannot preserve the reusable schedule library.

## Build a release

The release tag must point to the tested commit and match `const.py` and `manifest.json`. Publish as a prerelease. GitHub Actions' **Release** workflow builds the frontend and attaches **roommind.zip**. Wait for success and verify the asset against the tested package before installing through HACS.
