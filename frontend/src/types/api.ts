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
