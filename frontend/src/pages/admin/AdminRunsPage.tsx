import { useId, useMemo, useState, type JSX } from "react";

import { Link } from "react-router-dom";

import EmptyState from "@/components/states/EmptyState";
import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import StatusBadge from "@/components/states/StatusBadge";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAdminRuns } from "@/hooks/use-admin-runs";
import type { AdminRunSummary, RunStatus } from "@/types/api";

const STATUSES: readonly RunStatus[] = ["queued", "running", "succeeded", "failed", "canceled"];

/** Native-select styling matching the shadcn input/trigger surface. */
const SELECT_CLASS =
  "flex h-9 w-full items-center rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

/** Format an ISO timestamp for display, falling back to the raw value. */
function formatCreatedAt(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

interface RunRowProps {
  run: AdminRunSummary;
}

function RunRow({ run }: RunRowProps): JSX.Element {
  return (
    <TableRow>
      <TableCell className="font-medium">{run.user.email}</TableCell>
      <TableCell>
        <Link
          to={`/admin/runs/${run.id}`}
          className="font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {run.tool.name}
        </Link>{" "}
        <span className="text-xs text-muted-foreground">v{run.tool.version}</span>
      </TableCell>
      <TableCell>
        <StatusBadge status={run.status} />
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">
        <time dateTime={run.created_at}>{formatCreatedAt(run.created_at)}</time>
      </TableCell>
    </TableRow>
  );
}

/** Admin oversight screen listing every user's runs with a status filter. */
export default function AdminRunsPage(): JSX.Element {
  const statusId = useId();
  const [status, setStatus] = useState<RunStatus | "">("");

  const params = useMemo(() => (status ? { status } : {}), [status]);
  const { data, isLoading, isError, refetch } = useAdminRuns(params);

  const sorted = useMemo(
    () =>
      [...(data ?? [])].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    [data],
  );

  function handleStatusChange(event: React.ChangeEvent<HTMLSelectElement>): void {
    setStatus(event.target.value as RunStatus | "");
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
        <p className="text-sm text-muted-foreground">Oversee every user&apos;s runs.</p>
      </div>

      <div className="max-w-xs space-y-2">
        <Label htmlFor={statusId}>Filter by status</Label>
        <select id={statusId} className={SELECT_CLASS} value={status} onChange={handleStatusChange}>
          <option value="">All statuses</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <Loading label="Loading runs" />
      ) : isError ? (
        <ErrorState message="Failed to load runs." onRetry={() => void refetch()} />
      ) : sorted.length === 0 ? (
        <EmptyState title="No runs found" description="No runs match the selected status filter." />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <caption className="sr-only">All runs</caption>
            <TableHeader>
              <TableRow>
                <TableHead>Owner</TableHead>
                <TableHead>Tool</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((run) => (
                <RunRow key={run.id} run={run} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
