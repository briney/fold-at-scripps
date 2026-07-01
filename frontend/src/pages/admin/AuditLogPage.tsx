import type { JSX } from "react";

import EmptyState from "@/components/states/EmptyState";
import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuditLogs } from "@/hooks/use-admin-audit";
import type { AuditLogRead } from "@/types/api";

/** Format an ISO timestamp for display, falling back to the raw value. */
function formatCreatedAt(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

/** Render an entry's target as "type / id", or an em dash when absent. */
function formatTarget(entry: AuditLogRead): string {
  if (!entry.target_type && !entry.target_id) return "—";
  return [entry.target_type, entry.target_id].filter(Boolean).join(" / ");
}

interface AuditRowProps {
  entry: AuditLogRead;
}

function AuditRow({ entry }: AuditRowProps): JSX.Element {
  return (
    <TableRow>
      <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
        <time dateTime={entry.created_at}>{formatCreatedAt(entry.created_at)}</time>
      </TableCell>
      <TableCell className="font-mono text-xs">{entry.actor_id ?? "—"}</TableCell>
      <TableCell className="font-medium">{entry.action}</TableCell>
      <TableCell className="text-sm">{formatTarget(entry)}</TableCell>
      <TableCell className="max-w-xs">
        {entry.details ? (
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
            {JSON.stringify(entry.details)}
          </pre>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
    </TableRow>
  );
}

/** Admin audit-log screen listing recent actor actions, newest-first. */
export default function AuditLogPage(): JSX.Element {
  const { data, isLoading, isError, refetch } = useAuditLogs();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
        <p className="text-sm text-muted-foreground">
          Recent administrative actions, newest first.
        </p>
      </div>

      {isLoading ? (
        <Loading label="Loading audit log" />
      ) : isError ? (
        <ErrorState message="Failed to load the audit log." onRetry={() => void refetch()} />
      ) : (data ?? []).length === 0 ? (
        <EmptyState
          title="No audit entries"
          description="No administrative actions recorded yet."
        />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <caption className="sr-only">Audit log entries</caption>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data ?? []).map((entry) => (
                <AuditRow key={entry.id} entry={entry} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
