import { describe, expect, it } from "vitest";
import { buildZodSchema } from "@/lib/schema-form/build-zod";
import type { JsonSchema } from "@/types/api";
import antifold from "./__fixtures__/antifold.json";
import ablang2 from "./__fixtures__/ablang2.json";

describe("buildZodSchema on real autobio schemas", () => {
  it("validates a correct antifold payload (file field as filename string)", () => {
    const schema = buildZodSchema(antifold as JsonSchema);
    expect(
      schema.safeParse({ structure_path: "b.pdb", num_sequences: 2, temperature: 0.1 }).success,
    ).toBe(true);
  });
  it("rejects an antifold payload missing the required structure_path", () => {
    const schema = buildZodSchema(antifold as JsonSchema);
    expect(schema.safeParse({ num_sequences: 2 }).success).toBe(false);
  });
  it("coerces/accepts anyOf:[T,null] fields as nullable/optional (ablang2 layer)", () => {
    const schema = buildZodSchema(ablang2 as JsonSchema);
    expect(schema.safeParse({ sequences: ["EVQ"], layer: null }).success).toBe(true);
    expect(schema.safeParse({ sequences: ["EVQ"] }).success).toBe(true);
  });
  it("requires ablang2 sequences (a scalar array)", () => {
    const schema = buildZodSchema(ablang2 as JsonSchema);
    expect(schema.safeParse({}).success).toBe(false);
    expect(schema.safeParse({ sequences: "notarray" }).success).toBe(false);
  });
});

describe("buildZodSchema field-kind mapping (inline schemas for enum/boolean)", () => {
  it("maps enum -> restricted string set", () => {
    const s = buildZodSchema({
      type: "object",
      required: ["mode"],
      properties: { mode: { type: "string", enum: ["fast", "slow"] } },
    });
    expect(s.safeParse({ mode: "fast" }).success).toBe(true);
    expect(s.safeParse({ mode: "nope" }).success).toBe(false);
  });
  it("maps boolean and integer(min) correctly", () => {
    const s = buildZodSchema({
      type: "object",
      properties: { flag: { type: "boolean" }, n: { type: "integer", minimum: 1 } },
    });
    expect(s.safeParse({ flag: true, n: 3 }).success).toBe(true);
    expect(s.safeParse({ n: 0 }).success).toBe(false);
    expect(s.safeParse({ n: 1.5 }).success).toBe(false);
  });
});
