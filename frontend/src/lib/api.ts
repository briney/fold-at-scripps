import type { RunRead, RunSummary, ToolRead, ToolSummary, UserRead } from "@/types/api";

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
