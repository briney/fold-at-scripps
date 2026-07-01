import { useId } from "react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export interface JsonFieldProps {
  /** Form field name (schema property key). */
  name: string;
  /** Human-readable label text. */
  label: string;
  /** Optional help text rendered below the control. */
  description?: string;
  /** Whether the field is required (renders a `*` after the label). */
  required?: boolean;
  /** Raw JSON text currently in the editor. */
  value: string;
  /** Validation error message to display. */
  error?: string;
  /** Called with the raw text on every change. */
  onValueChange: (value: string) => void;
}

/**
 * JSON editor for schema fields that map to objects, arrays-of-objects, or
 * `additionalProperties` maps (e.g. `extra`, boltz2 `sequences`, antifold
 * `fixed_positions`). The raw text is `JSON.parse`d on submit by the parent
 * form; parse failures surface as a field error.
 */
export default function JsonField({
  name,
  label,
  description,
  required,
  value,
  error,
  onValueChange,
}: JsonFieldProps): React.JSX.Element {
  const id = useId();
  const describedBy = description ? `${id}-desc` : undefined;

  function handleChange(event: React.ChangeEvent<HTMLTextAreaElement>): void {
    onValueChange(event.target.value);
  }

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </Label>
      <Textarea
        id={id}
        name={name}
        value={value}
        aria-describedby={describedBy}
        aria-invalid={error ? true : undefined}
        onChange={handleChange}
        className="font-mono"
        rows={4}
      />
      {description ? (
        <p id={describedBy} className="text-sm text-muted-foreground">
          {description}
        </p>
      ) : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
