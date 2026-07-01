import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { listTools } from "@/lib/api";
import type { ToolSummary } from "@/types/api";

/** Fetch the full tool catalog from the `['tools']` query. */
export function useTools(): UseQueryResult<ToolSummary[]> {
  return useQuery({ queryKey: ["tools"], queryFn: () => listTools() });
}
