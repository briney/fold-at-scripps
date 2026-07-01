import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { toast } from "sonner";

import {
  adminAddAllowedEmail,
  adminListAllowedEmails,
  adminRemoveAllowedEmail,
  ApiError,
} from "@/lib/api";
import type { AllowedEmailRead } from "@/types/api";

const ALLOWED_EMAILS_KEY = ["admin", "allowed-emails"] as const;

/** Resolve a mutation error to a user-facing message. */
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Something went wrong";
}

/** Fetch the allowlist from the `['admin','allowed-emails']` query. */
export function useAllowedEmails(): UseQueryResult<AllowedEmailRead[]> {
  return useQuery({ queryKey: ALLOWED_EMAILS_KEY, queryFn: adminListAllowedEmails });
}

/** Add an email to the allowlist, invalidating the list and toasting on success/error. */
export function useAddAllowedEmail(): UseMutationResult<AllowedEmailRead, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (email: string) => adminAddAllowedEmail(email),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ALLOWED_EMAILS_KEY });
      toast.success("Email added to allowlist");
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}

/** Remove an email from the allowlist, invalidating the list and toasting on success/error. */
export function useRemoveAllowedEmail(): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => adminRemoveAllowedEmail(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ALLOWED_EMAILS_KEY });
      toast.success("Email removed from allowlist");
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}
