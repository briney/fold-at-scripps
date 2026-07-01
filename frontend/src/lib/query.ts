import { QueryClient } from "@tanstack/react-query";

/** Create a QueryClient with retries and window-focus refetching disabled. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
}
