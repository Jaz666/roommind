// @vitest-environment happy-dom
import { afterEach, expect, test, vi } from "vitest";
import { RsRoomDetail } from "./rs-room-detail";
import type { DeviceConfig, HassArea, HomeAssistant, RoomConfig } from "../types";

interface EditorInternals {
  _devices: DeviceConfig[];
  _displayName: string;
  _initFromConfig(): void;
  _doSave(): Promise<void>;
  _onDeviceChanged(e: CustomEvent<{ devices: DeviceConfig[] }>): void;
}

afterEach(() => vi.useRealTimers());

function editor() {
  const element = new RsRoomDetail();
  const callWS = vi.fn().mockResolvedValue({});
  element.hass = { language: "en", callWS } as unknown as HomeAssistant;
  element.area = { area_id: "bedroom" } as HassArea;
  element.config = {
    area_id: "bedroom",
    display_name: "Bedroom",
    devices: [
      {
        entity_id: "climate.bedroom_ac",
        type: "ac",
        role: "auto",
        energy_sensor: "sensor.ac_energy",
        obsolete_fork_option: true,
      },
    ],
  } as unknown as RoomConfig;
  const internal = element as unknown as EditorInternals;
  internal._initFromConfig();
  return { internal, callWS };
}

test("stale device properties do not make an unrelated room edit resend all devices", async () => {
  const { internal, callWS } = editor();
  internal._displayName = "Master Bedroom";
  await internal._doSave();
  expect(callWS).toHaveBeenCalledExactlyOnceWith({
    type: "roommind/rooms/save",
    area_id: "bedroom",
    display_name: "Master Bedroom",
  });
});

test.each([
  ["idle_action", "setback"],
  ["setback_auto_off", true],
  ["setpoint_mode", "direct"],
  ["setpoint_offset", 0.5],
  ["coil_dry", "on"],
  ["coil_dry_minutes", 25],
  ["coil_dry_mode", "dry"],
  ["coil_dry_fan_mode", "__keep__"],
] as const)("AC %s edits send the supported change without stale fields", async (key, value) => {
  vi.useFakeTimers();
  const { internal, callWS } = editor();
  internal._onDeviceChanged(
    new CustomEvent("device-changed", {
      detail: { devices: [{ ...internal._devices[0], [key]: value }] },
    }),
  );
  await vi.advanceTimersByTimeAsync(500);
  const payload = JSON.parse(JSON.stringify(callWS.mock.calls[0][0]));
  expect(payload).toEqual({
    type: "roommind/rooms/save",
    area_id: "bedroom",
    devices: [{ entity_id: "climate.bedroom_ac", type: "ac", role: "auto", [key]: value }],
  });
});
