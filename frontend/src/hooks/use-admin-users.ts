import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { adminCreatePasswordReset, adminListUsers, adminUpdateUser, ApiError } from "@/lib/api";
import type { AdminUserRead, AdminUserUpdate, PasswordResetResponse } from "@/types/api";

const USERS_KEY = ["admin", "users"] as const;

/** Resolve a mutation error to a user-facing message. */
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Something went wrong";
}

/** Fetch the full admin user list from the `['admin','users']` query. */
export function useAdminUsers(): UseQueryResult<AdminUserRead[]> {
  return useQuery({ queryKey: USERS_KEY, queryFn: adminListUsers });
}

export interface UpdateUserVars {
  id: string;
  changes: AdminUserUpdate;
}

/** Patch a user, invalidating the user list and toasting on success/error. */
export function useUpdateUser(): UseMutationResult<AdminUserRead, unknown, UpdateUserVars> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: UpdateUserVars) => adminUpdateUser(id, changes),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: USERS_KEY });
      toast.success("User updated");
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}

/** Mint a one-time password-reset token, invalidating the user list on success. */
export function useCreatePasswordReset(): UseMutationResult<
  PasswordResetResponse,
  unknown,
  string
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => adminCreatePasswordReset(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: USERS_KEY });
      toast.success("Password reset token created");
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}
