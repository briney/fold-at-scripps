import { useId } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface FileFieldProps {
  /** Form field name (schema property key). */
  name: string;
  /** Human-readable label text. */
  label: string;
  /** Optional help text rendered below the control. */
  description?: string;
  /** Whether the field is required (renders a `*` after the label). */
  required?: boolean;
  /** Name of the currently selected file, if any. */
  fileName?: string;
  /** Validation error message to display. */
  error?: string;
  /** Called with the selected file (or `null` when cleared). */
  onFileChange: (file: File | null) => void;
}

/**
 * File-upload widget for schema `string` fields with `format: "path"`.
 *
 * Reads the selected file from the native `<input type="file">` element's
 * `files` list (a `FileList`) rather than relying on `instanceof File`, so it
 * works in the test environment where native/jsdom `File` classes differ.
 */
export default function FileField({
  name,
  label,
  description,
  required,
  fileName,
  error,
  onFileChange,
}: FileFieldProps): React.JSX.Element {
  const id = useId();
  const describedBy = description ? `${id}-desc` : undefined;

  function handleChange(event: React.ChangeEvent<HTMLInputElement>): void {
    const selected = event.target.files;
    onFileChange(selected && selected.length > 0 ? selected[0] : null);
  }

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </Label>
      <Input
        id={id}
        name={name}
        type="file"
        required={required}
        aria-describedby={describedBy}
        aria-invalid={error ? true : undefined}
        onChange={handleChange}
      />
      {fileName ? <p className="text-sm text-muted-foreground">{fileName}</p> : null}
      {description ? (
        <p id={describedBy} className="text-sm text-muted-foreground">
          {description}
        </p>
      ) : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
