import type { JSX } from "react";

import { useParams } from "react-router-dom";

import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import StatusBadge from "@/components/states/StatusBadge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useAdminCancelRun, useAdminRun } from "@/hooks/use-admin-runs";
import { adminArtifactUrl, ApiError } from "@/lib/api";
import type { AdminRunRead, ArtifactRead } from "@/types/api";

/** Format an ISO timestamp for display, falling back to the raw value. */
function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

/** Render a byte count in a human-readable form (e.g. "5 B", "1.2 KB"). */
function formatBytes(bytes: number | null): string {
  if (bytes === null) return "unknown size";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"] as const;
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

/** Format an arbitrary param value for display in the definition list. */
function formatParamValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return String(value);
  return JSON.stringify(value);
}

interface OwnerProps {
  run: AdminRunRead;
}

function Owner({ run }: OwnerProps): JSX.Element {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
      <dt className="text-muted-foreground">Email</dt>
      <dd className="font-medium">{run.user.email}</dd>
      <dt className="text-muted-foreground">Name</dt>
      <dd>{run.user.display_name}</dd>
    </dl>
  );
}

interface TimingProps {
  run: AdminRunRead;
}

function Timing({ run }: TimingProps): JSX.Element {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
      <dt className="text-muted-foreground">Created</dt>
      <dd>
        <time dateTime={run.created_at}>{formatTimestamp(run.created_at)}</time>
      </dd>
      {run.started_at ? (
        <>
          <dt className="text-muted-foreground">Started</dt>
          <dd>
            <time dateTime={run.started_at}>{formatTimestamp(run.started_at)}</time>
          </dd>
        </>
      ) : null}
      {run.finished_at ? (
        <>
          <dt className="text-muted-foreground">Finished</dt>
          <dd>
            <time dateTime={run.finished_at}>{formatTimestamp(run.finished_at)}</time>
          </dd>
        </>
      ) : null}
      {run.wall_time_seconds !== null ? (
        <>
          <dt className="text-muted-foreground">Wall time</dt>
          <dd>{run.wall_time_seconds}s</dd>
        </>
      ) : null}
      {run.gpu_seconds !== null ? (
        <>
          <dt className="text-muted-foreground">GPU time</dt>
          <dd>{run.gpu_seconds}s</dd>
        </>
      ) : null}
    </dl>
  );
}

interface ParamsListProps {
  params: Record<string, unknown>;
}

function ParamsList({ params }: ParamsListProps): JSX.Element {
  const entries = Object.entries(params);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No parameters were submitted.</p>;
  }
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="font-medium">{key}</dt>
          <dd className="break-all text-muted-foreground">{formatParamValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

interface ArtifactListProps {
  runId: string;
  artifacts: ArtifactRead[];
}

function ArtifactList({ runId, artifacts }: ArtifactListProps): JSX.Element {
  if (artifacts.length === 0) {
    return <p className="text-sm text-muted-foreground">No artifacts are available yet.</p>;
  }
  return (
    <ul className="divide-y rounded-lg border">
      {artifacts.map((artifact) => (
        <li key={artifact.path} className="flex items-center justify-between px-4 py-3">
          <a
            href={adminArtifactUrl(runId, artifact.path)}
            download
            className="font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {artifact.name}
          </a>
          <span className="text-xs text-muted-foreground">{formatBytes(artifact.size_bytes)}</span>
        </li>
      ))}
    </ul>
  );
}

interface CancelRunDialogProps {
  runId: string;
  onConfirm: (id: string) => void;
  canceling: boolean;
}

function CancelRunDialog({ runId, onConfirm, canceling }: CancelRunDialogProps): JSX.Element {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button type="button" variant="outline" disabled={canceling}>
          Cancel
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Cancel this run?</AlertDialogTitle>
          <AlertDialogDescription>
            The queued run will be canceled and will not execute. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep run</AlertDialogCancel>
          <AlertDialogAction onClick={() => onConfirm(runId)}>Cancel run</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Admin-facing detail view for any user's run, with live polling and cancel. */
export default function AdminRunDetailPage(): JSX.Element {
  const { runId = "" } = useParams<{ runId: string }>();
  const cancelMutation = useAdminCancelRun();
  const { data, isLoading, isError, error, refetch } = useAdminRun(runId);

  function handleCancel(id: string): void {
    cancelMutation.mutate(id);
  }

  if (isLoading) {
    return <Loading label="Loading run" />;
  }

  if (isError) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">Run not found</h1>
          <p className="text-sm text-muted-foreground">This run does not exist.</p>
        </div>
      );
    }
    return <ErrorState message="Failed to load run." onRetry={() => void refetch()} />;
  }

  if (!data) {
    return <ErrorState message="Failed to load run." onRetry={() => void refetch()} />;
  }

  const run = data;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            {run.tool.name}{" "}
            <span className="text-base font-normal text-muted-foreground">v{run.tool.version}</span>
          </h1>
          <StatusBadge status={run.status} />
        </div>
        {run.status === "queued" ? (
          <CancelRunDialog
            runId={run.id}
            onConfirm={handleCancel}
            canceling={cancelMutation.isPending}
          />
        ) : null}
      </header>

      {run.status === "failed" && run.error ? (
        <div role="alert" className="rounded-lg border border-destructive/40 p-4 text-sm">
          <p className="font-medium text-destructive">Run failed</p>
          <p className="mt-1 whitespace-pre-wrap break-words text-destructive">{run.error}</p>
        </div>
      ) : null}

      <section aria-labelledby="owner-heading" className="space-y-3">
        <h2 id="owner-heading" className="text-lg font-semibold tracking-tight">
          Owner
        </h2>
        <Owner run={run} />
      </section>

      <section aria-labelledby="timing-heading" className="space-y-3">
        <h2 id="timing-heading" className="text-lg font-semibold tracking-tight">
          Timing
        </h2>
        <Timing run={run} />
      </section>

      <section aria-labelledby="params-heading" className="space-y-3">
        <h2 id="params-heading" className="text-lg font-semibold tracking-tight">
          Parameters
        </h2>
        <ParamsList params={run.params} />
      </section>

      <section aria-labelledby="artifacts-heading" className="space-y-3">
        <h2 id="artifacts-heading" className="text-lg font-semibold tracking-tight">
          Artifacts
        </h2>
        <ArtifactList runId={run.id} artifacts={run.artifacts} />
      </section>
    </div>
  );
}
