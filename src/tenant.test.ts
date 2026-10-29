import { expect, test } from "bun:test";
import { environment } from "./tenant.js";

test("tenant environment defaults to production", () => {
  expect(environment()).toBe("prod");
  expect(environment("test")).toBe("staging");
  expect(environment("prod")).toBe("prod");
});
