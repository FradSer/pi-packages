/** Phase-2 wire contract: the native write schema under strict sampling.
 * A sibling `harnessCases` field cannot be emitted by a strict-capable
 * provider; `content` is an unconstrained string and is the only channel that
 * survives the real wire. This test pins the fact, not an implementation. */
import { expect, test } from "bun:test";
import { Type } from "typebox";
import { getJsonSchemaToolParameters } from "../../../node_modules/@earendil-works/pi-coding-agent/dist/bundle/chunks/chunk-7O7QKK6A.js";
import { HARNESS_WRITE_PARAMETERS } from "../extensions/guardrails.ts";

const writeParameters = Type.Object({
  path: Type.String({ description: "Path to the file to write" }),
  content: Type.String({ description: "Content to write" }),
});

function strictWriteSchema(): Record<string, unknown> {
  return getJsonSchemaToolParameters({
    name: "write",
    parameters: writeParameters,
    constrainedSampling: { type: "json_schema", strict: "prefer" },
  }, true) as Record<string, unknown>;
}

test("strict sampling forbids any sibling field on native write", () => {
  const schema = strictWriteSchema();
  expect(schema.additionalProperties).toBe(false);
  expect(schema.required).toEqual(["path", "content"]);
  expect(Object.keys((schema.properties ?? {}) as Record<string, unknown>).sort()).toEqual(["content", "path"]);
});

test("content is an unconstrained string that can carry a case envelope", () => {
  const schema = strictWriteSchema();
  const content = (schema.properties as Record<string, Record<string, unknown>>).content;
  expect(content.type).toBe("string");
  expect(content.maxLength).toBeUndefined();
  expect(content.pattern).toBeUndefined();
  const envelope = JSON.stringify({
    rules: [{ id: "d0", text: "\\bD0\\b", action: "block" }],
    harnessCases: [{ ruleId: "d0", input: "维护 D0", matches: true }, { ruleId: "d0", input: "本地配色", matches: false }],
  });
  expect(typeof envelope).toBe("string");
  expect(JSON.parse(envelope).harnessCases).toHaveLength(2);
});

test("the declared harness_write tool emits cases on a strict provider wire", () => {
  const schema = getJsonSchemaToolParameters({
    name: "harness_write",
    parameters: HARNESS_WRITE_PARAMETERS,
    constrainedSampling: { type: "json_schema", strict: "prefer" },
  }, true) as Record<string, unknown>;
  expect(schema.additionalProperties).toBe(false);
  expect(schema.required).toEqual(["path", "content", "cases"]);
  const properties = schema.properties as Record<string, Record<string, unknown>>;
  expect(properties.cases.type).toBe("array");
  expect(properties.cases.items).toBeDefined();
  const items = properties.cases.items as Record<string, unknown>;
  expect(items.additionalProperties).toBe(false);
  expect((items.required as string[]).slice().sort()).toEqual(["input", "matches", "ruleId"]);
});

test("harness_write cases are required, not optional, so strict sampling cannot drop them", () => {
  const properties = HARNESS_WRITE_PARAMETERS.properties as Record<string, Record<string, unknown>>;
  expect(HARNESS_WRITE_PARAMETERS.required).toEqual(["path", "content", "cases"]);
  expect(properties.cases.anyOf).toBeUndefined();
  expect(properties.cases.type).toBe("array");
});
