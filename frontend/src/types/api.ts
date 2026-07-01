export type UserRole = "user" | "admin";
export type UserTier = "standard" | "power";
export type UserStatus = "pending" | "active" | "disabled";
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

export interface UserRead {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  tier: UserTier;
  status: UserStatus;
}
export interface ToolSummary {
  id: string;
  name: string;
  version: string;
  category: string;
  gpu_count: number;
  description: string | null;
  supports_batch: boolean;
}
export interface JsonSchema {
  type?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  enum?: unknown[];
  anyOf?: JsonSchema[];
  format?: string;
  default?: unknown;
  title?: string;
  description?: string;
  minimum?: number;
  maximum?: number;
  additionalProperties?: boolean | JsonSchema;
}
export interface ToolRead extends ToolSummary {
  image_tag: string | null;
  default_timeout: number | null;
  input_schema: JsonSchema;
}
export interface ToolRef {
  id: string;
  name: string;
  version: string;
  category: string;
}
export interface ArtifactRead {
  name: string;
  path: string;
  size_bytes: number | null;
  content_type: string | null;
}
export interface RunSummary {
  id: string;
  tool: ToolRef;
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
export interface RunRead extends RunSummary {
  params: Record<string, unknown>;
  assigned_gpu_ids: number[] | null;
  wall_time_seconds: number | null;
  gpu_seconds: number | null;
  error: string | null;
  artifacts: ArtifactRead[];
}

const TERMINAL: ReadonlySet<RunStatus> = new Set<RunStatus>(["succeeded", "failed", "canceled"]);
export function isTerminal(status: RunStatus): boolean {
  return TERMINAL.has(status);
}

export interface AdminUserRead {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  tier: UserTier;
  status: UserStatus;
  max_concurrent_runs_override: number | null;
  created_at: string;
}
export interface AdminUserUpdate {
  status?: UserStatus;
  tier?: UserTier;
  max_concurrent_runs_override?: number | null;
}
export interface AllowedEmailRead {
  id: string;
  email: string;
  created_at: string;
}
export interface SystemSettingsRead {
  maintenance_mode: boolean;
  standard_max_concurrent_runs: number;
  power_max_concurrent_runs: number;
  updated_at: string;
}
export interface SystemSettingsUpdate {
  maintenance_mode?: boolean;
  standard_max_concurrent_runs?: number;
  power_max_concurrent_runs?: number;
}
export interface ToolAdminRead {
  id: string;
  name: string;
  version: string;
  category: string;
  enabled: boolean;
  gpu_count: number;
  description: string | null;
  image_tag: string | null;
  default_timeout: number | null;
  supports_batch: boolean;
}
export interface CatalogSyncResult {
  added: number;
  updated: number;
}
export interface UserRef {
  id: string;
  email: string;
  display_name: string;
}
export interface AdminRunSummary {
  id: string;
  tool: ToolRef;
  user: UserRef;
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
export interface AdminRunRead extends AdminRunSummary {
  params: Record<string, unknown>;
  assigned_gpu_ids: number[] | null;
  wall_time_seconds: number | null;
  gpu_seconds: number | null;
  error: string | null;
  artifacts: ArtifactRead[];
}
export interface AuditLogRead {
  id: string;
  actor_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}
export interface PasswordResetResponse {
  token: string;
  expires_at: string;
}
