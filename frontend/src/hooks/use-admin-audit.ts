import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { adminListAuditLogs } from "@/lib/api";
import type { AuditLogRead } from "@/types/api";

/** Fetch audit-log entries (newest-first from the backend), optionally capped by `limit`. */
export function useAuditLogs(limit?: number): UseQueryResult<AuditLogRead[]> {
  return useQuery({
    queryKey: ["admin", "audit"],
    queryFn: () => adminListAuditLogs(limit),
  });
}
