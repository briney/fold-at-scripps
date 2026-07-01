import type { JsonSchema } from "@/types/api";

/** Widget kind chosen for a top-level schema property. */
export type FieldKind =
  "enum" | "file" | "text" | "textarea" | "number" | "boolean" | "string-array" | "json";

export interface FieldDescriptor {
  /** Schema property key / form field name. */
  name: string;
  /** Resolved (nullable-unwrapped) schema for the field. */
  schema: JsonSchema;
  /** Chosen widget kind. */
  kind: FieldKind;
  /** Human-readable label. */
  label: string;
  /** Help text, if any. */
  description?: string;
  /** Whether the field is required by the schema. */
  required: boolean;
  /** Enum options (for `kind === "enum"`). */
  options: string[];
  /** Schema `default`, if provided. */
  default?: unknown;
}

/** Unwrap `anyOf: [T, null]` to the concrete `T`; otherwise return as-is. */
function unwrapNullable(schema: JsonSchema): JsonSchema {
  if (Array.isArray(schema.anyOf)) {
    const nonNull = schema.anyOf.filter((s) => s.type !== "null");
    if (nonNull.length === 1) return nonNull[0];
  }
  return schema;
}

/** Title-case a snake_case / camelCase key for use as a fallback label. */
function humanize(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Heuristic: does the description suggest a multi-line text value? */
function isMultiline(description?: string): boolean {
  if (!description) return false;
  return /multi-?line|multiple lines|paragraph|json|newline/i.test(description);
}

function pickKind(inner: JsonSchema): FieldKind {
  if (Array.isArray(inner.enum) && inner.enum.length > 0) return "enum";
  if (inner.type === "string") {
    if (inner.format === "path") return "file";
    return isMultiline(inner.description) ? "textarea" : "text";
  }
  if (inner.type === "integer" || inner.type === "number") return "number";
  if (inner.type === "boolean") return "boolean";
  if (inner.type === "array") {
    const item = inner.items;
    const scalarItem =
      item && (item.type === "string" || item.type === "integer" || item.type === "number");
    return scalarItem ? "string-array" : "json";
  }
  // objects, additionalProperties maps, or anything unrecognized
  return "json";
}

/** Build a descriptor for a single top-level property. */
export function describeField(name: string, raw: JsonSchema, required: boolean): FieldDescriptor {
  const inner = unwrapNullable(raw);
  const kind = pickKind(inner);
  const options = kind === "enum" && Array.isArray(inner.enum) ? inner.enum.map(String) : [];
  return {
    name,
    schema: inner,
    kind,
    label: inner.title ?? humanize(name),
    description: inner.description,
    required,
    options,
    default: raw.default,
  };
}

/** Whether a field renders in the guided (top) section rather than Advanced. */
export function isGuided(field: FieldDescriptor): boolean {
  const scalarKinds: ReadonlySet<FieldKind> = new Set([
    "enum",
    "file",
    "text",
    "textarea",
    "number",
    "boolean",
  ]);
  return field.required && scalarKinds.has(field.kind);
}

/** Build descriptors for every top-level property, in declaration order. */
export function describeFields(schema: JsonSchema): FieldDescriptor[] {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  return Object.entries(properties).map(([name, prop]) =>
    describeField(name, prop, required.has(name)),
  );
}
