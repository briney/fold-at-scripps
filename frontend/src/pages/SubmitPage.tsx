import { useState, type JSX } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import ErrorState from "@/components/states/ErrorState";
import Loading from "@/components/states/Loading";
import { ApiError, getTool, submitRun } from "@/lib/api";
import SchemaForm from "@/lib/schema-form/SchemaForm";
import type { RunRead, ToolRead } from "@/types/api";

interface SubmitVariables {
  values: Record<string, unknown>;
  files: File[];
}

/** Map an API error to a researcher-facing message. */
function messageForError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) return `Invalid parameters: ${error.detail}`;
    if (error.status === 429) return `Quota reached: ${error.detail}`;
  }
  return "Something went wrong submitting this run. Please try again.";
}

/** Parameter-entry page that submits a run for a given tool. */
export default function SubmitPage(): JSX.Element {
  const { toolId } = useParams<{ toolId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    data: tool,
    isLoading,
    isError,
    refetch,
  } = useQuery<ToolRead>({
    queryKey: ["tool", toolId],
    queryFn: () => getTool(toolId as string),
    enabled: toolId !== undefined,
  });

  const mutation = useMutation<RunRead, unknown, SubmitVariables>({
    mutationFn: ({ values, files }) => submitRun((tool as ToolRead).id, values, files),
    onSuccess: (run) => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${run.id}`);
    },
    onError: (error) => {
      setSubmitError(messageForError(error));
    },
  });

  function handleSubmit(data: SubmitVariables): void {
    setSubmitError(null);
    mutation.mutate(data);
  }

  if (isLoading) return <Loading label="Loading tool" />;
  if (isError || !tool)
    return <ErrorState message="Failed to load tool." onRetry={() => void refetch()} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{tool.name}</h1>
        {tool.description ? (
          <p className="text-sm text-muted-foreground">{tool.description}</p>
        ) : null}
      </div>

      {submitError ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/40 p-4 text-sm text-destructive"
        >
          {submitError}
        </div>
      ) : null}

      <SchemaForm tool={tool} onSubmit={handleSubmit} submitting={mutation.isPending} />
    </div>
  );
}
