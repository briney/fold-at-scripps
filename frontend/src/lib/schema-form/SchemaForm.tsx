import { useMemo, useRef, useState } from "react";
import { useForm, type FieldValues, type Resolver, type UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { buildZodSchema } from "@/lib/schema-form/build-zod";
import FileField from "@/lib/schema-form/fields/FileField";
import JsonField from "@/lib/schema-form/fields/JsonField";
import { describeFields, isGuided, type FieldDescriptor } from "@/lib/schema-form/fields/describe";
import type { ToolRead } from "@/types/api";

export interface SchemaFormProps {
  tool: ToolRead;
  onSubmit: (data: { values: Record<string, unknown>; files: File[] }) => void;
  submitting?: boolean;
}

/** The `react-hook-form` API shape shared across the field renderers. */
type SchemaFormApi = UseFormReturn<FieldValues>;

/** Seed RHF default values from schema `default`s (best-effort, per field kind). */
function buildDefaults(fields: FieldDescriptor[]): FieldValues {
  const defaults: FieldValues = {};
  for (const field of fields) {
    if (field.kind === "file" || field.kind === "json") continue;
    if (field.default !== undefined && field.default !== null) {
      defaults[field.name] = field.default;
    } else if (field.kind === "boolean") {
      defaults[field.name] = false;
    } else if (field.kind === "string-array") {
      defaults[field.name] = [];
    }
  }
  return defaults;
}

/** Seed JSON editor text from schema `default`s (stringified) or empty. */
function buildJsonText(fields: FieldDescriptor[]): Record<string, string> {
  const text: Record<string, string> = {};
  for (const field of fields) {
    if (field.kind !== "json") continue;
    text[field.name] =
      field.default !== undefined && field.default !== null
        ? JSON.stringify(field.default, null, 2)
        : "";
  }
  return text;
}

export default function SchemaForm({
  tool,
  onSubmit,
  submitting,
}: SchemaFormProps): React.JSX.Element {
  const fields = useMemo(() => describeFields(tool.input_schema), [tool.input_schema]);
  // buildZodSchema returns z.ZodType with `unknown` output, while RHF's
  // resolver is keyed on FieldValues. The runtime schema is correct; we only
  // adapt the static type at this single boundary.
  const resolver = useMemo<Resolver<FieldValues>>(() => {
    const schema = buildZodSchema(tool.input_schema);
    return zodResolver(schema as Parameters<typeof zodResolver>[0]) as Resolver<FieldValues>;
  }, [tool.input_schema]);

  const form = useForm<FieldValues>({
    resolver,
    defaultValues: useMemo(() => buildDefaults(fields), [fields]),
  });

  const filesRef = useRef<Record<string, File>>({});
  const [fileNames, setFileNames] = useState<Record<string, string>>({});
  const [jsonText, setJsonText] = useState<Record<string, string>>(() => buildJsonText(fields));
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const guided = fields.filter(isGuided);
  const advanced = fields.filter((f) => !isGuided(f));

  function handleFileChange(name: string, file: File | null): void {
    if (file) {
      filesRef.current[name] = file;
      setFileNames((prev) => ({ ...prev, [name]: file.name }));
      form.setValue(name, file.name, { shouldValidate: true });
    } else {
      delete filesRef.current[name];
      setFileNames((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
      form.setValue(name, undefined, { shouldValidate: true });
    }
  }

  function handleJsonChange(name: string, value: string): void {
    setJsonText((prev) => ({ ...prev, [name]: value }));
    form.clearErrors(name);
  }

  function parseJsonFields(): { values: Record<string, unknown>; ok: boolean } {
    const parsed: Record<string, unknown> = {};
    let ok = true;
    for (const field of fields) {
      if (field.kind !== "json") continue;
      const raw = jsonText[field.name]?.trim();
      if (!raw) continue;
      try {
        parsed[field.name] = JSON.parse(raw);
      } catch {
        ok = false;
        form.setError(field.name, { type: "manual", message: "Enter valid JSON" });
      }
    }
    return { values: parsed, ok };
  }

  function handleFormSubmit(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const json = parseJsonFields();
    if (!json.ok) return;
    void form.handleSubmit((values) => {
      const merged: Record<string, unknown> = { ...values, ...json.values };
      for (const [name, file] of Object.entries(filesRef.current)) {
        merged[name] = file.name;
      }
      onSubmit({ values: merged, files: Object.values(filesRef.current) });
    })(event);
  }

  return (
    <form onSubmit={handleFormSubmit} noValidate className="space-y-6">
      <div className="space-y-4">
        {guided.map((field) => (
          <FieldRenderer
            key={field.name}
            field={field}
            form={form}
            fileName={fileNames[field.name]}
            jsonValue={jsonText[field.name] ?? ""}
            onFileChange={handleFileChange}
            onJsonChange={handleJsonChange}
          />
        ))}
      </div>

      {advanced.length > 0 ? (
        <div className="rounded-md border p-4">
          <button
            type="button"
            aria-expanded={advancedOpen}
            aria-controls="advanced-options-panel"
            className="cursor-pointer text-sm font-medium"
            onClick={() => setAdvancedOpen((open) => !open)}
          >
            Advanced options
          </button>
          {advancedOpen ? (
            <div id="advanced-options-panel" className="mt-4 space-y-4">
              {advanced.map((field) => (
                <FieldRenderer
                  key={field.name}
                  field={field}
                  form={form}
                  fileName={fileNames[field.name]}
                  jsonValue={jsonText[field.name] ?? ""}
                  onFileChange={handleFileChange}
                  onJsonChange={handleJsonChange}
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <Button type="submit" disabled={submitting}>
        {submitting ? "Submitting…" : "Submit"}
      </Button>
    </form>
  );
}

interface FieldRendererProps {
  field: FieldDescriptor;
  form: SchemaFormApi;
  fileName?: string;
  jsonValue: string;
  onFileChange: (name: string, file: File | null) => void;
  onJsonChange: (name: string, value: string) => void;
}

function FieldRenderer({
  field,
  form,
  fileName,
  jsonValue,
  onFileChange,
  onJsonChange,
}: FieldRendererProps): React.JSX.Element {
  const error = form.formState.errors[field.name]?.message as string | undefined;

  if (field.kind === "file") {
    return (
      <FileField
        name={field.name}
        label={field.label}
        description={field.description}
        required={field.required}
        fileName={fileName}
        error={error}
        onFileChange={(file) => onFileChange(field.name, file)}
      />
    );
  }

  if (field.kind === "json") {
    return (
      <JsonField
        name={field.name}
        label={field.label}
        description={field.description}
        required={field.required}
        value={jsonValue}
        error={error}
        onValueChange={(value) => onJsonChange(field.name, value)}
      />
    );
  }

  return <ScalarField field={field} form={form} error={error} />;
}

interface ScalarFieldProps {
  field: FieldDescriptor;
  form: SchemaFormApi;
  error?: string;
}

function ScalarField({ field, form, error }: ScalarFieldProps): React.JSX.Element {
  const id = `field-${field.name}`;
  const descId = field.description ? `${id}-desc` : undefined;

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {field.label}
        {field.required ? <span aria-hidden="true"> *</span> : null}
      </Label>
      <ScalarControl field={field} form={form} id={id} descId={descId} hasError={!!error} />
      {field.description ? (
        <p id={descId} className="text-sm text-muted-foreground">
          {field.description}
        </p>
      ) : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}

interface ScalarControlProps {
  field: FieldDescriptor;
  form: SchemaFormApi;
  id: string;
  descId?: string;
  hasError: boolean;
}

function ScalarControl({
  field,
  form,
  id,
  descId,
  hasError,
}: ScalarControlProps): React.JSX.Element {
  const common = {
    id,
    "aria-describedby": descId,
    "aria-invalid": hasError ? true : undefined,
  } as const;

  switch (field.kind) {
    case "enum":
      return (
        <Select
          value={(form.watch(field.name) as string | undefined) ?? ""}
          onValueChange={(value) => form.setValue(field.name, value, { shouldValidate: true })}
        >
          <SelectTrigger
            id={id}
            aria-describedby={descId}
            aria-invalid={hasError ? true : undefined}
          >
            <SelectValue placeholder="Select…" />
          </SelectTrigger>
          <SelectContent>
            {field.options.map((opt) => (
              <SelectItem key={opt} value={opt}>
                {opt}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    case "boolean":
      return (
        <Switch
          id={id}
          aria-describedby={descId}
          checked={!!form.watch(field.name)}
          onCheckedChange={(checked) =>
            form.setValue(field.name, checked, { shouldValidate: true })
          }
        />
      );
    case "number":
      return (
        <Input
          type="number"
          step="any"
          {...common}
          {...form.register(field.name, { valueAsNumber: true })}
        />
      );
    case "textarea":
      return <Textarea {...common} {...form.register(field.name)} />;
    case "string-array":
      return (
        <StringArrayField field={field} form={form} id={id} descId={descId} hasError={hasError} />
      );
    default:
      return <Input type="text" {...common} {...form.register(field.name)} />;
  }
}

interface StringArrayFieldProps {
  field: FieldDescriptor;
  form: SchemaFormApi;
  id: string;
  descId?: string;
  hasError: boolean;
}

function StringArrayField({
  field,
  form,
  id,
  descId,
  hasError,
}: StringArrayFieldProps): React.JSX.Element {
  const value = (form.watch(field.name) as string[] | undefined) ?? [];
  const rows = value.length > 0 ? value : [""];

  function updateRow(index: number, next: string): void {
    const draft = [...rows];
    draft[index] = next;
    form.setValue(
      field.name,
      draft.filter((v) => v !== ""),
      { shouldValidate: true },
    );
  }

  function addRow(): void {
    form.setValue(field.name, [...value, ""], { shouldValidate: false });
  }

  function removeRow(index: number): void {
    form.setValue(
      field.name,
      rows.filter((_, i) => i !== index).filter((v) => v !== ""),
      { shouldValidate: true },
    );
  }

  return (
    <div className="space-y-2">
      {rows.map((row, index) => (
        <div key={index} className="flex gap-2">
          <Input
            id={index === 0 ? id : undefined}
            aria-describedby={index === 0 ? descId : undefined}
            aria-invalid={index === 0 && hasError ? true : undefined}
            aria-label={`${field.label} ${index + 1}`}
            value={row}
            onChange={(event) => updateRow(index, event.target.value)}
          />
          <Button type="button" variant="outline" size="sm" onClick={() => removeRow(index)}>
            Remove
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={addRow}>
        Add
      </Button>
    </div>
  );
}
