import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError, cancelRun, deleteRun, listRuns } from "@/lib/api";
import { isTerminal, type RunRead, type RunSummary } from "@/types/api";

/** Resolve a mutation error to a user-facing message. */
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Something went wrong";
}

/**
 * Fetch all runs, polling every 2.5s while any run is non-terminal and
 * stopping once every run has reached a terminal status.
 */
export function useRuns(): UseQueryResult<RunSummary[]> {
  return useQuery({
    queryKey: ["runs"],
    queryFn: listRuns,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((run) => !isTerminal(run.status)) ? 2500 : false,
  });
}

/** Cancel a queued run, refreshing the runs list and that run's detail on success. */
export function useCancelRun(): UseMutationResult<RunRead, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => cancelRun(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["run", id] });
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}

/** Delete (hide) a run, refreshing the runs list on success. */
export function useDeleteRun(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteRun(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}
