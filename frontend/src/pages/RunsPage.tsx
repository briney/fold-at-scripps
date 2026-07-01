import { useMemo, type JSX } from "react";

import { Link } from "react-router-dom";

import EmptyState from "@/components/states/EmptyState";
import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import StatusBadge from "@/components/states/StatusBadge";
import { Button } from "@/components/ui/button";
import { useCancelRun, useDeleteRun, useRuns } from "@/hooks/use-runs";
import type { RunSummary } from "@/types/api";

/** Format an ISO timestamp for display, falling back to the raw value. */
function formatCreatedAt(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

interface RunRowProps {
  run: RunSummary;
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
  canceling: boolean;
  deleting: boolean;
}

function RunRow({ run, onCancel, onDelete, canceling, deleting }: RunRowProps): JSX.Element {
  function handleCancel(): void {
    onCancel(run.id);
  }

  function handleDelete(): void {
    onDelete(run.id);
  }

  return (
    <tr className="border-b last:border-0">
      <td className="px-4 py-3">
        <Link
          to={`/runs/${run.id}`}
          className="font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {run.tool.name}
        </Link>{" "}
        <span className="text-xs text-muted-foreground">v{run.tool.version}</span>
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={run.status} />
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        <time dateTime={run.created_at}>{formatCreatedAt(run.created_at)}</time>
      </td>
      <td className="px-4 py-3">
        <div className="flex justify-end gap-2">
          {run.status === "queued" ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCancel}
              disabled={canceling}
            >
              Cancel
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleDelete}
            disabled={deleting}
          >
            Delete
          </Button>
        </div>
      </td>
    </tr>
  );
}

/** Researcher-facing list of runs with live polling, cancel, and delete. */
export default function RunsPage(): JSX.Element {
  const { data, isLoading, isError, refetch } = useRuns();
  const cancelMutation = useCancelRun();
  const deleteMutation = useDeleteRun();

  const sorted = useMemo(
    () =>
      [...(data ?? [])].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    [data],
  );

  function handleCancel(id: string): void {
    cancelMutation.mutate(id);
  }

  function handleDelete(id: string): void {
    deleteMutation.mutate(id);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
        <p className="text-sm text-muted-foreground">Track and manage your submitted runs.</p>
      </div>

      {isLoading ? (
        <Loading label="Loading runs" />
      ) : isError ? (
        <ErrorState message="Failed to load runs." onRetry={() => void refetch()} />
      ) : sorted.length === 0 ? (
        <EmptyState title="No runs yet" description="Submit a tool to see runs appear here." />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-left">
            <caption className="sr-only">Your runs</caption>
            <thead>
              <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                <th scope="col" className="px-4 py-2 font-medium">
                  Tool
                </th>
                <th scope="col" className="px-4 py-2 font-medium">
                  Status
                </th>
                <th scope="col" className="px-4 py-2 font-medium">
                  Created
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((run) => (
                <RunRow
                  key={run.id}
                  run={run}
                  onCancel={handleCancel}
                  onDelete={handleDelete}
                  canceling={cancelMutation.isPending}
                  deleting={deleteMutation.isPending}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
