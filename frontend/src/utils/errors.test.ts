import { expect, test } from "vitest";
import { errorText } from "./errors";

test("settings validation errors retain the field path returned by Home Assistant", () => {
  const message = "extra keys not allowed @ data['devices'][0]['energy_sensor']";
  expect(errorText({ code: "invalid_format", message }, "Failed", "en")).toContain(message);
  expect(errorText({ error: { code: "invalid_format", message } }, "Failed", "en")).toContain(
    message,
  );
});

test("validation failures without detail and other errors still use localized messages", () => {
  expect(errorText({ code: "invalid_format" }, "Failed", "en")).toBe(
    "A value is out of its allowed range and was not saved.",
  );
  expect(errorText({ code: "unauthorized", message: "raw" }, "Failed", "en")).not.toBe("raw");
  expect(errorText({ message: "Connection closed" }, "Failed", "en")).toBe("Connection closed");
});
