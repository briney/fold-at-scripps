import type { JSX, ReactNode } from "react";

export interface EmptyStateProps {
  /** Short primary message describing the empty condition. */
  title: string;
  /** Optional supporting detail rendered below the title. */
  description?: string;
  /** Optional action (e.g. a link or button) rendered below the text. */
  action?: ReactNode;
}

/** Neutral placeholder shown when a collection has no items to display. */
export default function EmptyState({ title, description, action }: EmptyStateProps): JSX.Element {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}
