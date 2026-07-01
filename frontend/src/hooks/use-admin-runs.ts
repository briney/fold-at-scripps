import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { adminCancelRun, adminGetRun, adminListRuns, ApiError } from "@/lib/api";
import { isTerminal, type AdminRunRead, type AdminRunSummary, type RunStatus } from "@/types/api";

export interface AdminRunsParams {
  userId?: string;
  status?: RunStatus;
}

/** Resolve a mutation error to a user-facing message. */
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Something went wrong";
}

/** Fetch every user's runs, optionally filtered by owner and/or status. */
export function useAdminRuns(params: AdminRunsParams = {}): UseQueryResult<AdminRunSummary[]> {
  return useQuery({
    queryKey: ["admin", "runs", params],
    queryFn: () => adminListRuns(params),
  });
}

/**
 * Fetch a single run for admin oversight, polling every 2.5s until the run
 * reaches a terminal status.
 */
export function useAdminRun(id: string): UseQueryResult<AdminRunRead> {
  return useQuery({
    queryKey: ["admin", "run", id],
    queryFn: () => adminGetRun(id),
    refetchInterval: (query) => {
      const run = query.state.data;
      return run && isTerminal(run.status) ? false : 2500;
    },
  });
}

/** Cancel any user's queued run, refreshing the run list and detail, with toasts. */
export function useAdminCancelRun(): UseMutationResult<AdminRunRead, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => adminCancelRun(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "runs"] });
      void queryClient.invalidateQueries({ queryKey: ["admin", "run", id] });
      toast.success("Run canceled");
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}
