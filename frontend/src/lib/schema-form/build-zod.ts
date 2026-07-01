import { z } from "zod";
import type { JsonSchema } from "@/types/api";

function unwrapNullable(schema: JsonSchema): { inner: JsonSchema; nullable: boolean } {
  if (Array.isArray(schema.anyOf)) {
    const nonNull = schema.anyOf.filter((s) => s.type !== "null");
    const nullable = schema.anyOf.some((s) => s.type === "null");
    if (nonNull.length === 1) return { inner: nonNull[0], nullable };
  }
  return { inner: schema, nullable: false };
}

function isScalar(schema: JsonSchema): boolean {
  return (
    schema.type === "string" ||
    schema.type === "integer" ||
    schema.type === "number" ||
    schema.type === "boolean"
  );
}

function fieldZod(schema: JsonSchema): z.ZodTypeAny {
  const { inner, nullable } = unwrapNullable(schema);
  let base: z.ZodTypeAny;
  if (Array.isArray(inner.enum) && inner.enum.length > 0) {
    base = z.enum(inner.enum.map(String) as [string, ...string[]]);
  } else if (inner.type === "string") {
    base = z.string();
  } else if (inner.type === "integer" || inner.type === "number") {
    let num = z.number();
    if (inner.type === "integer") num = num.int();
    if (typeof inner.minimum === "number") num = num.min(inner.minimum);
    if (typeof inner.maximum === "number") num = num.max(inner.maximum);
    base = num;
  } else if (inner.type === "boolean") {
    base = z.boolean();
  } else if (inner.type === "array") {
    // Scalar items get their concrete mapping; arrays-of-objects (e.g. $ref items)
    // fall back to unknown elements. Either way, the value must be an array so
    // non-array inputs are rejected (server validates element structure).
    const item = inner.items && isScalar(inner.items) ? fieldZod(inner.items) : z.unknown();
    base = z.array(item);
  } else {
    base = z.unknown(); // objects, additionalProperties: server-validated
  }
  return nullable ? base.nullable() : base;
}

export function buildZodSchema(schema: JsonSchema): z.ZodType {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const [key, prop] of Object.entries(properties)) {
    const field = fieldZod(prop);
    shape[key] = required.has(key) ? field : field.optional();
  }
  return z.object(shape).passthrough();
}
