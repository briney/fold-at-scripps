import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { adminListTools, adminSetToolEnabled, adminSyncCatalog, ApiError } from "@/lib/api";
import type { CatalogSyncResult, ToolAdminRead } from "@/types/api";

const TOOLS_KEY = ["admin", "tools"] as const;

/** Resolve a mutation error to a user-facing message. */
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Something went wrong";
}

/** Fetch all tools (including disabled) from the `['admin','tools']` query. */
export function useAdminTools(): UseQueryResult<ToolAdminRead[]> {
  return useQuery({ queryKey: TOOLS_KEY, queryFn: adminListTools });
}

export interface SetToolEnabledVars {
  id: string;
  enabled: boolean;
}

/** Enable or disable a tool, invalidating the list and toasting on success/error. */
export function useSetToolEnabled(): UseMutationResult<ToolAdminRead, unknown, SetToolEnabledVars> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: SetToolEnabledVars) => adminSetToolEnabled(id, enabled),
    onSuccess: (tool) => {
      void queryClient.invalidateQueries({ queryKey: TOOLS_KEY });
      toast.success(tool.enabled ? "Tool enabled" : "Tool disabled");
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}

/** Sync the catalog from source, invalidating the list and toasting counts on success. */
export function useSyncCatalog(): UseMutationResult<CatalogSyncResult, unknown, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => adminSyncCatalog(),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: TOOLS_KEY });
      toast.success(`${result.added} added, ${result.updated} updated`);
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}
