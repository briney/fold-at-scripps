import { useQuery } from "@tanstack/react-query";

import { getMe } from "@/lib/api";
import type { UserRead } from "@/types/api";

export interface AuthState {
  user: UserRead | undefined;
  isLoading: boolean;
  isError: boolean;
}

/** Read the current authenticated user from the `['me']` query. */
export function useAuth(): AuthState {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
    retry: false,
  });
  return { user: data, isLoading, isError };
}
