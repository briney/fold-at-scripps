import type { JSX } from "react";

import { Skeleton } from "@/components/ui/skeleton";

export interface LoadingProps {
  /** Accessible label announced to assistive technology. */
  label?: string;
}

/** Placeholder shown while a query is in flight. */
export default function Loading({ label = "Loading" }: LoadingProps): JSX.Element {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className="space-y-3">
      <span className="sr-only">{label}</span>
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-24 w-full" />
      ))}
    </div>
  );
}
