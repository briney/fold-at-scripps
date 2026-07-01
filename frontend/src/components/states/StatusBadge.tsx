import type { JSX } from "react";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RunStatus } from "@/types/api";

export interface StatusBadgeProps {
  /** Run lifecycle status to display. */
  status: RunStatus;
  /** Extra classes merged onto the badge. */
  className?: string;
}

interface StatusStyle {
  variant: BadgeProps["variant"];
  className: string;
}

const STATUS_STYLES: Record<RunStatus, StatusStyle> = {
  queued: { variant: "secondary", className: "" },
  running: {
    variant: "default",
    className: "border-transparent bg-blue-500 text-white hover:bg-blue-500/80",
  },
  succeeded: {
    variant: "default",
    className: "border-transparent bg-emerald-600 text-white hover:bg-emerald-600/80",
  },
  failed: { variant: "destructive", className: "" },
  canceled: { variant: "outline", className: "text-muted-foreground" },
};

/** Colored badge conveying a run's lifecycle status. */
export default function StatusBadge({ status, className }: StatusBadgeProps): JSX.Element {
  const style = STATUS_STYLES[status];
  return (
    <Badge variant={style.variant} className={cn(style.className, className)}>
      {status}
    </Badge>
  );
}
