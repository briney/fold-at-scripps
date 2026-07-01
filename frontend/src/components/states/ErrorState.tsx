import type { JSX } from "react";

import { Button } from "@/components/ui/button";

export interface ErrorStateProps {
  /** Message describing what went wrong. */
  message?: string;
  /** Invoked when the user clicks the retry button; when omitted, no button renders. */
  onRetry?: () => void;
}

/** Error surface with an optional retry action. */
export default function ErrorState({
  message = "Something went wrong.",
  onRetry,
}: ErrorStateProps): JSX.Element {
  function handleRetry(): void {
    onRetry?.();
  }

  return (
    <div role="alert" className="space-y-3 rounded-lg border border-destructive/40 p-6 text-sm">
      <p className="text-destructive">{message}</p>
      {onRetry ? (
        <Button type="button" variant="outline" onClick={handleRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
