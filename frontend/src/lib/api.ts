import type {
  AdminRunRead,
  AdminRunSummary,
  AdminUserRead,
  AdminUserUpdate,
  AllowedEmailRead,
  AuditLogRead,
  CatalogSyncResult,
  PasswordResetResponse,
  RunRead,
  RunStatus,
  RunSummary,
  SystemSettingsRead,
  SystemSettingsUpdate,
  ToolAdminRead,
  ToolRead,
  ToolSummary,
  UserRead,
} from "@/types/api";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // non-JSON error body: keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function jsonPost(data: unknown, method = "POST"): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
}

export const getMe = () => request<UserRead>("/auth/me");
export const login = (email: string, password: string) =>
  request<UserRead>("/auth/login", jsonPost({ email, password }));
export const register = (email: string, password: string, display_name: string) =>
  request<UserRead>("/auth/register", jsonPost({ email, password, display_name }));
export const logout = () => request<void>("/auth/logout", { method: "POST" });
export const redeemPasswordReset = (token: string, newPassword: string) =>
  request<void>("/auth/reset-password", jsonPost({ token, new_password: newPassword }));

export const listTools = (category?: string) =>
  request<ToolSummary[]>(`/tools${category ? `?category=${encodeURIComponent(category)}` : ""}`);
export const getTool = (id: string) => request<ToolRead>(`/tools/${id}`);

export function submitRun(toolId: string, params: Record<string, unknown>, files: File[]) {
  const form = new FormData();
  form.append("tool_id", toolId);
  form.append("params", JSON.stringify(params));
  for (const file of files) form.append("files", file);
  return request<RunRead>("/runs", { method: "POST", body: form });
}

export const listRuns = () => request<RunSummary[]>("/runs");
export const getRun = (id: string) => request<RunRead>(`/runs/${id}`);
export const cancelRun = (id: string) => request<RunRead>(`/runs/${id}/cancel`, { method: "POST" });
export const deleteRun = (id: string) => request<void>(`/runs/${id}`, { method: "DELETE" });
export const artifactUrl = (runId: string, path: string) =>
  `/runs/${runId}/artifacts/${path.split("/").map(encodeURIComponent).join("/")}`;

export const adminListUsers = () => request<AdminUserRead[]>("/admin/users");
export const adminGetUser = (id: string) => request<AdminUserRead>(`/admin/users/${id}`);
export const adminUpdateUser = (id: string, changes: AdminUserUpdate) =>
  request<AdminUserRead>(`/admin/users/${id}`, jsonPost(changes, "PATCH"));
export const adminCreatePasswordReset = (id: string) =>
  request<PasswordResetResponse>(`/admin/users/${id}/password-reset`, { method: "POST" });

export const adminListAllowedEmails = () => request<AllowedEmailRead[]>("/admin/allowed-emails");
export const adminAddAllowedEmail = (email: string) =>
  request<AllowedEmailRead>("/admin/allowed-emails", jsonPost({ email }));
export const adminRemoveAllowedEmail = (id: string) =>
  request<void>(`/admin/allowed-emails/${id}`, { method: "DELETE" });

export const adminGetSettings = () => request<SystemSettingsRead>("/admin/settings");
export const adminUpdateSettings = (changes: SystemSettingsUpdate) =>
  request<SystemSettingsRead>("/admin/settings", jsonPost(changes, "PATCH"));

export const adminListTools = () => request<ToolAdminRead[]>("/admin/tools");
export const adminSetToolEnabled = (id: string, enabled: boolean) =>
  request<ToolAdminRead>(`/admin/tools/${id}`, jsonPost({ enabled }, "PATCH"));
export const adminSyncCatalog = () =>
  request<CatalogSyncResult>("/admin/catalog/sync", { method: "POST" });

export function adminListRuns(params: { userId?: string; status?: RunStatus } = {}) {
  const qs = new URLSearchParams();
  if (params.userId) qs.set("user_id", params.userId);
  if (params.status) qs.set("status", params.status);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<AdminRunSummary[]>(`/admin/runs${suffix}`);
}
export const adminGetRun = (id: string) => request<AdminRunRead>(`/admin/runs/${id}`);
export const adminCancelRun = (id: string) =>
  request<AdminRunRead>(`/admin/runs/${id}/cancel`, { method: "POST" });

export const adminListAuditLogs = (limit?: number) =>
  request<AuditLogRead[]>(`/admin/audit-logs${limit ? `?limit=${limit}` : ""}`);

// Admin artifact download (admin-gated endpoint from Task 0). Mirrors the
// researcher `artifactUrl` but under /admin/runs; per-segment-encoded, keeps `/`.
export const adminArtifactUrl = (runId: string, path: string) =>
  `/admin/runs/${runId}/artifacts/${path.split("/").map(encodeURIComponent).join("/")}`;
