import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { adminGetSettings, adminUpdateSettings, ApiError } from "@/lib/api";
import type { SystemSettingsRead, SystemSettingsUpdate } from "@/types/api";

const SETTINGS_KEY = ["admin", "settings"] as const;

/** Resolve a mutation error to a user-facing message. */
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Something went wrong";
}

/** Fetch the current system settings from the `['admin','settings']` query. */
export function useAdminSettings(): UseQueryResult<SystemSettingsRead> {
  return useQuery({ queryKey: SETTINGS_KEY, queryFn: adminGetSettings });
}

/** Patch system settings, invalidating the cache and toasting on success/error. */
export function useUpdateSettings(): UseMutationResult<
  SystemSettingsRead,
  unknown,
  SystemSettingsUpdate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: SystemSettingsUpdate) => adminUpdateSettings(changes),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SETTINGS_KEY });
      toast.success("Settings saved");
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}
