# Admin Console (Plan 9b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the admin console — an admin-only `/admin` area with six management screens (users, allowlist, settings, catalog, job oversight, audit log) over the Plan 8 `/admin/*` APIs — on the shipped Plan 9a frontend foundation, with app-wide toast feedback.

**Architecture:** A thin extension of the 9a Vite/React/TS SPA. A `RequireAdmin` guard (nested inside the existing `RequireAuth`) gates an `AdminLayout` (secondary tab-nav + `<Outlet/>`) rendered inside the existing `AppShell`. Admin API client functions + TS types + TanStack Query hooks (keys namespaced under `['admin', …]`) drive the screens. Mutations give feedback via app-wide sonner toasts; the researcher cancel/delete mutations are retrofitted with error toasts. Everything reuses 9a (API client, auth, states, shadcn, test harness); no architectural divergence.

**Tech Stack:** Vite, React, TypeScript (strict), Tailwind, shadcn/ui (+ `table`, `alert-dialog`, existing `sonner`), lucide-react, React Router, TanStack Query, React Hook Form + Zod (where a form benefits), Vitest + Testing Library + userEvent + MSW.

## Global Constraints

- **Vite + React + TypeScript (strict)**; no `any` (use `unknown` + narrowing). No `.js`/`.jsx`.
- **Tailwind + shadcn/ui + lucide-react**; `cn()` for conditional classes. shadcn primitives are added non-interactively: `npx shadcn@latest add -y <component>`.
- **React Router**; **TanStack Query** for all server state; **React Hook Form + Zod** for non-trivial forms.
- **Vitest + @testing-library/react + userEvent + MSW**; query by role/label (not test IDs). Mock the API at the network level (MSW), not by stubbing `fetch`.
- Functional components only; `interface {ComponentName}Props`; files `PascalCase.tsx`; handlers `handle{Event}` / props `on{Event}`; semantic, accessible HTML.
- **No `instanceof File`/`Blob`** anywhere (the test env restores native `File` over jsdom).
- Run npm from `frontend/`. `npm run lint`, `npm test`, `npm run build` must all pass. **CI is unchanged** (the `frontend` job stays lint+test+build; no E2E).
- All API calls are relative same-origin paths via the existing `request<T>` helper (`credentials:"include"`, throws `ApiError{status,detail}` on non-2xx).

## Precision convention (read before executing)

- **Logic/contract code (Task 1: admin API client + types) is given in full** — implement it as written.
- **For UI/screen tasks, the Vitest test files given here ARE the behavioral contract — implement them (adapt only import paths).** The component prose is a structural spec (what to render, which hooks/api fns, which states, exact props/signatures, which shadcn components). You may write the JSX yourself, but **every prop, signature, route path, query key, hook name, and api-fn name another task depends on must match this plan exactly.**
- FastAPI error bodies are `{"detail": string}`; `ApiError.detail` carries that string.
- **Toast testing:** unit tests mock the toast module — `vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }))` — and assert the spy was called (avoids portal/timer flakiness). Import `toast` from `"sonner"` in components.

## Backend API contract (client + all MSW mocks must match)

- `GET /admin/users` → `AdminUserRead[]`; `GET /admin/users/{id}` → `AdminUserRead` (404); `PATCH /admin/users/{id}` body partial `{status?,tier?,max_concurrent_runs_override?}` → `AdminUserRead` (404).
- `POST /admin/users/{id}/password-reset` → 201 `PasswordResetResponse` (404).
- `GET /admin/allowed-emails` → `AllowedEmailRead[]`; `POST /admin/allowed-emails` body `{email}` → 201 `AllowedEmailRead` (409 dup); `DELETE /admin/allowed-emails/{id}` → 204 (404).
- `GET /admin/settings` → `SystemSettingsRead`; `PATCH /admin/settings` body partial → `SystemSettingsRead`.
- `GET /admin/tools` → `ToolAdminRead[]`; `PATCH /admin/tools/{id}` body `{enabled}` → `ToolAdminRead` (404); `POST /admin/catalog/sync` → `CatalogSyncResult`.
- `GET /admin/runs?user_id=&status=` → `AdminRunSummary[]`; `GET /admin/runs/{id}` → `AdminRunRead` (404); `POST /admin/runs/{id}/cancel` → `AdminRunRead` (404/409).
- `GET /admin/audit-logs?limit=` → `AuditLogRead[]`. (Note: API path is `/admin/audit-logs`; the frontend route is `/admin/audit`.)

## Query keys & routes (keep identical everywhere)

- Keys: `['admin','users']`, `['admin','allowed-emails']`, `['admin','settings']`, `['admin','tools']`, `['admin','runs', params]`, `['admin','run', id]`, `['admin','audit']`. Mutations invalidate the relevant key.
- Routes: `/admin` (index → `/admin/users`), `/admin/users`, `/admin/allowed-emails`, `/admin/settings`, `/admin/catalog`, `/admin/runs`, `/admin/runs/:runId`, `/admin/audit`.

## File Structure

```
frontend/
  vite.config.ts                 # (modify) add "/admin" to server.proxy
  src/
    main.tsx / App.tsx           # (modify) mount <Toaster/>; wire /admin routes
    types/api.ts                 # (modify) add admin types
    lib/api.ts                   # (modify) add admin client fns
    components/
      RequireAdmin.tsx           # (new) admin-only route guard
      ui/                        # (add) table.tsx, alert-dialog.tsx via shadcn
    hooks/
      use-runs.ts                # (modify) add onError toasts (retrofit)
      use-admin-users.ts         # (new)
      use-admin-access.ts        # (new) allowlist
      use-admin-settings.ts      # (new)
      use-admin-catalog.ts       # (new)
      use-admin-runs.ts          # (new)
      use-admin-audit.ts         # (new)
    pages/admin/
      AdminLayout.tsx            # (new) tab-nav + <Outlet/>
      UsersPage.tsx              # (new) + edit dialog + reset-token dialog
      AllowlistPage.tsx          # (new)
      SettingsPage.tsx           # (new)
      CatalogPage.tsx            # (new) ADMIN catalog (distinct from researcher pages/CatalogPage.tsx)
      AdminRunsPage.tsx          # (new)
      AdminRunDetailPage.tsx     # (new)
      AuditLogPage.tsx           # (new)
```

---

### Task 0: (Backend — implement FIRST) Admin artifact-download endpoint

This is a **Python/backend** task (uses `uv`/`pytest`/`ruff`, Postgres) — the one backend change in Plan 9b. It adds an admin-gated, non-owner-scoped artifact download so the admin run-detail links (Task 7) work for *any* user's run. Mirrors the researcher endpoint in `api/runs.py::download_artifact` but resolves the run via `admin_get_run` (which eager-loads `artifacts`) instead of the owner-scoped `get_run`.

**Files:**
- Modify: `src/fold_at_scripps/api/admin.py`
- Test: `tests/api/test_admin_runs.py`

**Interfaces:**
- Consumes: `admin_get_run(session, run_id)` (eager tool+user+artifacts, from Plan 8), `require_admin` (router-level), `get_storage`, `Storage`, `FileResponse`.
- Produces: `GET /admin/runs/{run_id}/artifacts/{artifact_path:path}` → streamed `FileResponse` (admin-gated; any owner; 404 for unknown run/artifact; traversal-guarded). Distinct path from `GET /admin/runs/{run_id}` and `POST /admin/runs/{run_id}/cancel` — no route conflict.

- [ ] **Step 1: Write the failing test** (add to `tests/api/test_admin_runs.py`, reusing its `_login_admin`, `_seed_tool`, `_user`, `_run` helpers, and the `_make_output` pattern from `tests/api/test_runs.py` — write a real output file + `Artifact` row for a run owned by a *different* (non-admin) user):

```python
async def test_admin_downloads_another_users_artifact(db_session: AsyncSession):
    tool = await _seed_tool(db_session)
    alice = await _user(db_session, "alice@scripps.edu")
    run = await _run(db_session, alice, tool, RunStatus.SUCCEEDED)
    # write a real output file + index it as an Artifact (mirror tests/api/test_runs.py::_make_output)
    from fold_at_scripps.models import Artifact
    from fold_at_scripps.storage import get_storage
    storage = get_storage()
    target = storage.outputs_dir(run.id) / "raw/result.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"HELLO")
    db_session.add(Artifact(run_id=run.id, name="result.txt", path="raw/result.txt",
                            content_type="text/plain", size_bytes=5))
    await db_session.commit()
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.get(f"/admin/runs/{run.id}/artifacts/raw/result.txt")
        assert resp.status_code == 200
        assert resp.content == b"HELLO"


async def test_admin_download_unknown_artifact_404(db_session: AsyncSession):
    tool = await _seed_tool(db_session)
    alice = await _user(db_session, "alice@scripps.edu")
    run = await _run(db_session, alice, tool, RunStatus.SUCCEEDED)
    async with _client() as client:
        await _login_admin(client, db_session)
        assert (await client.get(f"/admin/runs/{run.id}/artifacts/nope.txt")).status_code == 404
```

Run: `docker compose up -d postgres && uv run pytest tests/api/test_admin_runs.py -q` → FAIL (route missing / 404 on the download).

- [ ] **Step 2: Implement** in `src/fold_at_scripps/api/admin.py`. Extend imports: `from fastapi.responses import FileResponse` and `from fold_at_scripps.storage import Storage, get_storage`. Add the endpoint (place it near the other `/runs` routes):

```python
@router.get("/runs/{run_id}/artifacts/{artifact_path:path}")
async def admin_download_artifact(
    run_id: uuid.UUID,
    artifact_path: str,
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> FileResponse:
    """Stream any run's output file (admin-gated, traversal-guarded)."""
    run = await admin_get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    artifact = next((a for a in run.artifacts if a.path == artifact_path), None)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    outputs = storage.outputs_dir(run_id).resolve()
    target = (outputs / artifact_path).resolve()
    if not target.is_relative_to(outputs) or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    media_type = artifact.content_type or "application/octet-stream"
    return FileResponse(target, filename=artifact.name, media_type=media_type)
```

- [ ] **Step 3: Run tests + lint** → `uv run pytest tests/api/test_admin_runs.py -q` PASS; `uv run ruff check . && uv run ruff format --check .` clean; `uv run pytest -q` (full backend suite) green.

- [ ] **Step 4: Commit**

```bash
git add src/fold_at_scripps/api/admin.py tests/api/test_admin_runs.py
git commit -m "feat(admin): admin-scoped run artifact download endpoint"
```

---

### Task 1: Admin types + API client + Vite proxy

**Files:**
- Modify: `frontend/src/types/api.ts`, `frontend/src/lib/api.ts`, `frontend/vite.config.ts`
- Create: `frontend/src/lib/admin-api.test.ts`

**Interfaces:**
- Consumes: existing `request<T>`, `ApiError` (`lib/api.ts`); existing `RunStatus`/`UserRole`/`UserTier`/`UserStatus`/`ToolRef`/`ArtifactRead` (`types/api.ts`).
- Produces (types): `AdminUserRead`, `AdminUserUpdate`, `AllowedEmailRead`, `SystemSettingsRead`, `SystemSettingsUpdate`, `ToolAdminRead`, `CatalogSyncResult`, `UserRef`, `AdminRunSummary`, `AdminRunRead`, `AuditLogRead`, `PasswordResetResponse`.
- Produces (client): `adminListUsers`, `adminGetUser`, `adminUpdateUser`, `adminCreatePasswordReset`, `adminListAllowedEmails`, `adminAddAllowedEmail`, `adminRemoveAllowedEmail`, `adminGetSettings`, `adminUpdateSettings`, `adminListTools`, `adminSetToolEnabled`, `adminSyncCatalog`, `adminListRuns`, `adminGetRun`, `adminCancelRun`, `adminListAuditLogs`.

- [ ] **Step 1: Add the admin types**

Append to `frontend/src/types/api.ts` (uses the existing `UserRole`/`UserTier`/`UserStatus`/`RunStatus`/`ToolRef`/`ArtifactRead`):

```ts
export interface AdminUserRead {
  id: string; email: string; display_name: string;
  role: UserRole; tier: UserTier; status: UserStatus;
  max_concurrent_runs_override: number | null; created_at: string;
}
export interface AdminUserUpdate {
  status?: UserStatus; tier?: UserTier; max_concurrent_runs_override?: number | null;
}
export interface AllowedEmailRead { id: string; email: string; created_at: string; }
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
  id: string; name: string; version: string; category: string; enabled: boolean;
  gpu_count: number; description: string | null; image_tag: string | null;
  default_timeout: number | null; supports_batch: boolean;
}
export interface CatalogSyncResult { added: number; updated: number; }
export interface UserRef { id: string; email: string; display_name: string; }
export interface AdminRunSummary {
  id: string; tool: ToolRef; user: UserRef; status: RunStatus;
  created_at: string; started_at: string | null; finished_at: string | null;
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
  id: string; actor_id: string | null; action: string;
  target_type: string | null; target_id: string | null;
  details: Record<string, unknown> | null; created_at: string;
}
export interface PasswordResetResponse { token: string; expires_at: string; }
```

- [ ] **Step 2: Write the failing client tests**

Create `frontend/src/lib/admin-api.test.ts`:

```ts
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/lib/test/server";
import {
  ApiError,
  adminAddAllowedEmail,
  adminListRuns,
  adminListUsers,
  adminUpdateUser,
} from "@/lib/api";
import type { AdminUserRead } from "@/types/api";

const adminUser: AdminUserRead = {
  id: "u1", email: "a@scripps.edu", display_name: "A", role: "admin",
  tier: "power", status: "active", max_concurrent_runs_override: null,
  created_at: "2026-07-01T00:00:00Z",
};

describe("admin api client", () => {
  it("lists users (typed)", async () => {
    server.use(http.get("/admin/users", () => HttpResponse.json([adminUser])));
    await expect(adminListUsers()).resolves.toEqual([adminUser]);
  });

  it("throws ApiError with detail on 409 (duplicate allowlist email)", async () => {
    server.use(
      http.post("/admin/allowed-emails", () =>
        HttpResponse.json({ detail: "already on the allowlist" }, { status: 409 }),
      ),
    );
    await expect(adminAddAllowedEmail("dup@scripps.edu")).rejects.toBeInstanceOf(ApiError);
    await expect(adminAddAllowedEmail("dup@scripps.edu")).rejects.toMatchObject({ status: 409 });
  });

  it("PATCHes a user with a partial body", async () => {
    let seen: unknown = null;
    server.use(
      http.patch("/admin/users/u1", async ({ request }) => {
        seen = await request.json();
        return HttpResponse.json({ ...adminUser, tier: "standard" });
      }),
    );
    await adminUpdateUser("u1", { tier: "standard" });
    expect(seen).toEqual({ tier: "standard" });
  });

  it("builds the runs query string from filters", async () => {
    let url = "";
    server.use(
      http.get("/admin/runs", ({ request }) => {
        url = new URL(request.url).search;
        return HttpResponse.json([]);
      }),
    );
    await adminListRuns({ status: "queued", userId: "u1" });
    expect(url).toContain("status=queued");
    expect(url).toContain("user_id=u1");
  });
});
```

Run: `npm test -- admin-api` → FAIL (functions not exported).

- [ ] **Step 3: Implement the client functions**

Append to `frontend/src/lib/api.ts` (reuse the existing `request`, `jsonPost` helpers; add a small `jsonPatch` if not present):

```ts
import type {
  AdminRunRead, AdminRunSummary, AdminUserRead, AllowedEmailRead,
  AuditLogRead, CatalogSyncResult, PasswordResetResponse,
  SystemSettingsRead, ToolAdminRead,
} from "@/types/api";
import type { AdminUserUpdate, RunStatus, SystemSettingsUpdate } from "@/types/api";

function jsonBody(data: unknown, method: string): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
}

export const adminListUsers = () => request<AdminUserRead[]>("/admin/users");
export const adminGetUser = (id: string) => request<AdminUserRead>(`/admin/users/${id}`);
export const adminUpdateUser = (id: string, changes: AdminUserUpdate) =>
  request<AdminUserRead>(`/admin/users/${id}`, jsonBody(changes, "PATCH"));
export const adminCreatePasswordReset = (id: string) =>
  request<PasswordResetResponse>(`/admin/users/${id}/password-reset`, { method: "POST" });

export const adminListAllowedEmails = () =>
  request<AllowedEmailRead[]>("/admin/allowed-emails");
export const adminAddAllowedEmail = (email: string) =>
  request<AllowedEmailRead>("/admin/allowed-emails", jsonBody({ email }, "POST"));
export const adminRemoveAllowedEmail = (id: string) =>
  request<void>(`/admin/allowed-emails/${id}`, { method: "DELETE" });

export const adminGetSettings = () => request<SystemSettingsRead>("/admin/settings");
export const adminUpdateSettings = (changes: SystemSettingsUpdate) =>
  request<SystemSettingsRead>("/admin/settings", jsonBody(changes, "PATCH"));

export const adminListTools = () => request<ToolAdminRead[]>("/admin/tools");
export const adminSetToolEnabled = (id: string, enabled: boolean) =>
  request<ToolAdminRead>(`/admin/tools/${id}`, jsonBody({ enabled }, "PATCH"));
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
```

(If `jsonPost` already exists and is reused for POSTs, keep using it; the point is: PATCH/POST/DELETE with the correct methods, GET otherwise. Do not set `Content-Type` on the bodiless POSTs/DELETE.)

- [ ] **Step 4: Add `/admin` to the Vite dev proxy**

In `frontend/vite.config.ts`, add `"/admin": "http://localhost:8000"` to `server.proxy` (alongside the existing `/auth`, `/tools`, `/runs`, `/health`).

- [ ] **Step 5: Run tests + typecheck**

Run: `npm test -- admin-api` → PASS. Then `npm run lint` (run `prettier --write .` first) and `npm run build` → clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/lib/api.ts frontend/src/lib/admin-api.test.ts frontend/vite.config.ts
git commit -m "feat(frontend): admin API client + types + /admin dev proxy"
```

---

### Task 2: Admin shell — `RequireAdmin`, `AdminLayout`, routes, Toaster, shadcn primitives

**Files:**
- Create: `frontend/src/components/RequireAdmin.tsx`, `frontend/src/pages/admin/AdminLayout.tsx`, `frontend/src/components/RequireAdmin.test.tsx`, `frontend/src/pages/admin/AdminLayout.test.tsx`
- Modify: `frontend/src/App.tsx` (wire `/admin` routes + mount `<Toaster/>`), `frontend/src/main.tsx` (or `App.tsx`) for `<Toaster/>`
- Add: shadcn `table` + `alert-dialog` primitives (`npx shadcn@latest add -y table alert-dialog`)

**Interfaces:**
- Consumes: `useAuth` (`['me']`); React Router `Navigate`/`Outlet`/`NavLink`.
- Produces: `<RequireAdmin>` (renders `<Outlet/>` for admins; `<Navigate to="/" replace/>` for non-admins; spinner while `['me']` loads); `<AdminLayout>` (secondary tab-nav to the six screens + `<Outlet/>`). The `/admin` route tree.

- [ ] **Step 1: Add shadcn primitives + mount Toaster**

Run (from `frontend/`): `npx shadcn@latest add -y table alert-dialog`. Commit the generated `src/components/ui/table.tsx` and `src/components/ui/alert-dialog.tsx`.

Mount the toaster once — in `App.tsx` render `<Toaster />` (import from `@/components/ui/sonner`) as a sibling of the routes so toasts appear on every screen.

- [ ] **Step 2: Write the failing tests**

`frontend/src/components/RequireAdmin.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import RequireAdmin from "@/components/RequireAdmin";

function tree() {
  return (
    <Routes>
      <Route path="/" element={<h1>Home</h1>} />
      <Route element={<RequireAdmin />}>
        <Route path="/admin" element={<h1>Admin Area</h1>} />
      </Route>
    </Routes>
  );
}

const base = { id: "u1", email: "a@scripps.edu", display_name: "A", tier: "standard", status: "active" };

test("renders admin content for an admin", async () => {
  server.use(http.get("/auth/me", () => HttpResponse.json({ ...base, role: "admin" })));
  renderWithProviders(tree(), { route: "/admin" });
  expect(await screen.findByRole("heading", { name: /admin area/i })).toBeInTheDocument();
});

test("redirects a non-admin away from /admin", async () => {
  server.use(http.get("/auth/me", () => HttpResponse.json({ ...base, role: "user" })));
  renderWithProviders(tree(), { route: "/admin" });
  await waitFor(() => expect(screen.getByRole("heading", { name: /home/i })).toBeInTheDocument());
});
```

`frontend/src/pages/admin/AdminLayout.test.tsx`:

```tsx
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/lib/test/render";
import AdminLayout from "@/pages/admin/AdminLayout";

test("shows the six admin tab links", () => {
  renderWithProviders(
    <Routes><Route element={<AdminLayout />}><Route path="/admin" element={<div />} /></Route></Routes>,
    { route: "/admin" },
  );
  for (const name of [/users/i, /allowlist/i, /settings/i, /catalog/i, /runs/i, /audit/i]) {
    expect(screen.getByRole("link", { name })).toBeInTheDocument();
  }
});
```

Run: `npm test -- RequireAdmin AdminLayout` → FAIL (modules missing).

- [ ] **Step 3: Implement**

- `RequireAdmin.tsx`: `const { user, isLoading } = useAuth();` → `isLoading` → `<div role="status">…</div>`; `!user || user.role !== "admin"` → `<Navigate to="/" replace />`; else `<Outlet />`.
- `AdminLayout.tsx`: a `<nav>` of `<NavLink>`s — `to="/admin/users"` "Users", `/admin/allowed-emails` "Allowlist", `/admin/settings` "Settings", `/admin/catalog` "Catalog", `/admin/runs` "Runs", `/admin/audit` "Audit" — plus `<Outlet/>` below. Active-link styling via `cn()`.
- `App.tsx`: under the existing protected `AppShell` route, add:

```tsx
<Route path="admin" element={<RequireAdmin />}>
  <Route element={<AdminLayout />}>
    <Route index element={<Navigate to="/admin/users" replace />} />
    <Route path="users" element={<UsersPage />} />
    <Route path="allowed-emails" element={<AllowlistPage />} />
    <Route path="settings" element={<SettingsPage />} />
    <Route path="catalog" element={<AdminCatalogPage />} />
    <Route path="runs" element={<AdminRunsPage />} />
    <Route path="runs/:runId" element={<AdminRunDetailPage />} />
    <Route path="audit" element={<AuditLogPage />} />
  </Route>
</Route>
```

Use placeholder `<h1>` components for screens not yet built (Tasks 3–8 replace them) so routing compiles. `AdminCatalogPage` is the import alias for `pages/admin/CatalogPage.tsx` (avoid a name clash with the researcher `pages/CatalogPage.tsx`).

- [ ] **Step 4: Run tests** → `npm test` PASS (whole suite). Then `npm run lint` + `npm run build` clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RequireAdmin.tsx frontend/src/components/RequireAdmin.test.tsx frontend/src/pages/admin/AdminLayout.tsx frontend/src/pages/admin/AdminLayout.test.tsx frontend/src/App.tsx frontend/src/components/ui/table.tsx frontend/src/components/ui/alert-dialog.tsx
git commit -m "feat(frontend): admin shell (RequireAdmin guard, AdminLayout, routes, Toaster)"
```

---

### Task 3: Users screen (list, edit dialog, password-reset dialog)

**Files:**
- Create: `frontend/src/hooks/use-admin-users.ts`, `frontend/src/pages/admin/UsersPage.tsx`, `frontend/src/pages/admin/UsersPage.test.tsx`
- Modify: `frontend/src/App.tsx` (wire real `UsersPage`)

**Interfaces:**
- Consumes: `adminListUsers`, `adminUpdateUser`, `adminCreatePasswordReset`, `ApiError`; `AdminUserRead`/`AdminUserUpdate`/`PasswordResetResponse`; shadcn `Table`/`Dialog`/`Select`/`Input`/`Button`/`Badge`; `toast`.
- Produces: `useAdminUsers()` (`['admin','users']`), `useUpdateUser()` + `useCreatePasswordReset()` mutations (invalidate `['admin','users']`; toast); `<UsersPage>` at `/admin/users`.

**UsersPage:** table of users (email, display_name, role, tier, status badge, quota override). A labelled "Search users" input filters by email/status (filter-in-render). Row action **Edit** opens a shadcn `Dialog` with a small form (status `Select`, tier `Select`, `max_concurrent_runs_override` number input; empty → `null`) → `useUpdateUser` → on success `toast.success("User updated")` + close + invalidate. Row action **Reset password** → `useCreatePasswordReset` → on success open a `Dialog` showing `token` (in a readonly input + a Copy button) with a "shown once — convey out of band" warning. Loading/error/empty states via `states/*`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/admin/UsersPage.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import UsersPage from "@/pages/admin/UsersPage";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));
import { toast } from "sonner";

const users = [
  { id: "u1", email: "alice@scripps.edu", display_name: "Alice", role: "user", tier: "standard", status: "active", max_concurrent_runs_override: null, created_at: "2026-07-01T00:00:00Z" },
  { id: "u2", email: "bob@scripps.edu", display_name: "Bob", role: "user", tier: "standard", status: "pending", max_concurrent_runs_override: null, created_at: "2026-07-01T00:00:00Z" },
];

function tree() {
  return <Routes><Route path="/admin/users" element={<UsersPage />} /></Routes>;
}

test("lists users and filters by search", async () => {
  server.use(http.get("/admin/users", () => HttpResponse.json(users)));
  renderWithProviders(tree(), { route: "/admin/users" });
  expect(await screen.findByText("alice@scripps.edu")).toBeInTheDocument();
  expect(screen.getByText("bob@scripps.edu")).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText(/search users/i), "alice");
  expect(screen.queryByText("bob@scripps.edu")).not.toBeInTheDocument();
});

test("edits a user's tier and toasts success", async () => {
  server.use(
    http.get("/admin/users", () => HttpResponse.json(users)),
    http.patch("/admin/users/u1", () => HttpResponse.json({ ...users[0], tier: "power" })),
  );
  renderWithProviders(tree(), { route: "/admin/users" });
  const row = (await screen.findByText("alice@scripps.edu")).closest("tr")!;
  await userEvent.click(within(row).getByRole("button", { name: /edit/i }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.selectOptions(within(dialog).getByLabelText(/tier/i), "power");
  await userEvent.click(within(dialog).getByRole("button", { name: /save/i }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalled());
});

test("reset password shows the one-time token", async () => {
  server.use(
    http.get("/admin/users", () => HttpResponse.json(users)),
    http.post("/admin/users/u1/password-reset", () =>
      HttpResponse.json({ token: "SECRET-TOKEN-123", expires_at: "2026-07-02T00:00:00Z" }, { status: 201 }),
    ),
  );
  renderWithProviders(tree(), { route: "/admin/users" });
  const row = (await screen.findByText("alice@scripps.edu")).closest("tr")!;
  await userEvent.click(within(row).getByRole("button", { name: /reset password/i }));
  expect(await screen.findByDisplayValue("SECRET-TOKEN-123")).toBeInTheDocument();
});
```

Run: `npm test -- UsersPage` → FAIL.

- [ ] **Step 2: Implement** `use-admin-users.ts`, `UsersPage.tsx` (+ the two dialogs) per spec; wire `/admin/users`.
- [ ] **Step 3: Run tests** → PASS. Then `npm run lint` + `npm run build`.
- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-admin-users.ts frontend/src/pages/admin/UsersPage.tsx frontend/src/pages/admin/UsersPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): admin users screen (edit + password reset)"
```

---

### Task 4: Allowlist screen

**Files:**
- Create: `frontend/src/hooks/use-admin-access.ts`, `frontend/src/pages/admin/AllowlistPage.tsx`, `frontend/src/pages/admin/AllowlistPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `adminListAllowedEmails`, `adminAddAllowedEmail`, `adminRemoveAllowedEmail`, `ApiError`; shadcn `Table`/`Input`/`Button`/`AlertDialog`; `toast`.
- Produces: `useAllowedEmails()` (`['admin','allowed-emails']`), `useAddAllowedEmail()`/`useRemoveAllowedEmail()` (invalidate + toast); `<AllowlistPage>` at `/admin/allowed-emails`.

**AllowlistPage:** table (email, created_at). An "Add email" labelled input + Add button → `useAddAllowedEmail` (on 409 → `toast.error(err.detail)`; on success → toast + clear input). Per-row **Remove** opens a shadcn `AlertDialog` confirm → `useRemoveAllowedEmail` → toast. States via `states/*`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/admin/AllowlistPage.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import AllowlistPage from "@/pages/admin/AllowlistPage";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));
import { toast } from "sonner";

const rows = [{ id: "e1", email: "approved@scripps.edu", created_at: "2026-07-01T00:00:00Z" }];
function tree() { return <Routes><Route path="/admin/allowed-emails" element={<AllowlistPage />} /></Routes>; }

test("lists allowlisted emails", async () => {
  server.use(http.get("/admin/allowed-emails", () => HttpResponse.json(rows)));
  renderWithProviders(tree(), { route: "/admin/allowed-emails" });
  expect(await screen.findByText("approved@scripps.edu")).toBeInTheDocument();
});

test("shows an error toast when adding a duplicate", async () => {
  server.use(
    http.get("/admin/allowed-emails", () => HttpResponse.json(rows)),
    http.post("/admin/allowed-emails", () => HttpResponse.json({ detail: "already on the allowlist" }, { status: 409 })),
  );
  renderWithProviders(tree(), { route: "/admin/allowed-emails" });
  await userEvent.type(await screen.findByLabelText(/add email/i), "approved@scripps.edu");
  await userEvent.click(screen.getByRole("button", { name: /^add$/i }));
  await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/allowlist/i)));
});

test("removes an email after confirming", async () => {
  server.use(
    http.get("/admin/allowed-emails", () => HttpResponse.json(rows)),
    http.delete("/admin/allowed-emails/e1", () => new HttpResponse(null, { status: 204 })),
  );
  renderWithProviders(tree(), { route: "/admin/allowed-emails" });
  await userEvent.click(await screen.findByRole("button", { name: /remove/i }));
  const dialog = await screen.findByRole("alertdialog");
  await userEvent.click(within(dialog).getByRole("button", { name: /remove|confirm/i }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalled());
});
```
(Add `import { within } from "@testing-library/react";`.)

Run: `npm test -- AllowlistPage` → FAIL.

- [ ] **Step 2: Implement** hook + page; wire route.
- [ ] **Step 3: Run tests** → PASS; `npm run lint` + `npm run build`.
- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-admin-access.ts frontend/src/pages/admin/AllowlistPage.tsx frontend/src/pages/admin/AllowlistPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): admin allowlist screen"
```

---

### Task 5: Settings screen

**Files:**
- Create: `frontend/src/hooks/use-admin-settings.ts`, `frontend/src/pages/admin/SettingsPage.tsx`, `frontend/src/pages/admin/SettingsPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `adminGetSettings`, `adminUpdateSettings`; `SystemSettingsRead`/`SystemSettingsUpdate`; shadcn `Switch`/`Input`/`Label`/`Button`; `toast`.
- Produces: `useAdminSettings()` (`['admin','settings']`), `useUpdateSettings()` (invalidate + toast); `<SettingsPage>` at `/admin/settings`.

**SettingsPage:** fetch settings; a form (RHF + Zod) with `maintenance_mode` `Switch`, `standard_max_concurrent_runs` + `power_max_concurrent_runs` numeric inputs (Zod `int().min(0)`), seeded from the fetched values. Save → `useUpdateSettings(payload)` → `toast.success("Settings saved")`. Loading/error states.

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/admin/SettingsPage.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import SettingsPage from "@/pages/admin/SettingsPage";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));
import { toast } from "sonner";

const settings = { maintenance_mode: false, standard_max_concurrent_runs: 3, power_max_concurrent_runs: 12, updated_at: "2026-07-01T00:00:00Z" };
function tree() { return <Routes><Route path="/admin/settings" element={<SettingsPage />} /></Routes>; }

test("loads current settings and saves changes", async () => {
  let sent: unknown = null;
  server.use(
    http.get("/admin/settings", () => HttpResponse.json(settings)),
    http.patch("/admin/settings", async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json({ ...settings, standard_max_concurrent_runs: 5 });
    }),
  );
  renderWithProviders(tree(), { route: "/admin/settings" });
  const std = await screen.findByLabelText(/standard/i);
  await userEvent.clear(std);
  await userEvent.type(std, "5");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalled());
  expect(sent).toMatchObject({ standard_max_concurrent_runs: 5 });
});
```

Run: `npm test -- SettingsPage` → FAIL.

- [ ] **Step 2: Implement** hook + page; wire route.
- [ ] **Step 3: Run tests** → PASS; `npm run lint` + `npm run build`.
- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-admin-settings.ts frontend/src/pages/admin/SettingsPage.tsx frontend/src/pages/admin/SettingsPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): admin settings screen"
```

---

### Task 6: Catalog screen (admin)

**Files:**
- Create: `frontend/src/hooks/use-admin-catalog.ts`, `frontend/src/pages/admin/CatalogPage.tsx`, `frontend/src/pages/admin/CatalogPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `adminListTools`, `adminSetToolEnabled`, `adminSyncCatalog`; `ToolAdminRead`/`CatalogSyncResult`; shadcn `Table`/`Switch`/`Button`/`Input`; `toast`.
- Produces: `useAdminTools()` (`['admin','tools']`), `useSetToolEnabled()`/`useSyncCatalog()` (invalidate `['admin','tools']` + toast); `<CatalogPage>` (imported as `AdminCatalogPage`) at `/admin/catalog`.

**CatalogPage (admin):** table of ALL tools (name, version, category, enabled `Switch`). Toggling calls `useSetToolEnabled(id, next)` → toast. A "Sync catalog" button → `useSyncCatalog()` → on success `toast.success(`${added} added, ${updated} updated`)` + invalidate. A "Search tools" filter (filter-in-render). States via `states/*`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/admin/CatalogPage.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import CatalogPage from "@/pages/admin/CatalogPage";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));
import { toast } from "sonner";

const tools = [
  { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding", enabled: true, gpu_count: 1, description: "d", image_tag: "a:1", default_timeout: 600, supports_batch: false },
  { id: "t2", name: "ablang2", version: "1.0.0", category: "embedding", enabled: false, gpu_count: 1, description: "d", image_tag: "b:1", default_timeout: 600, supports_batch: true },
];
function tree() { return <Routes><Route path="/admin/catalog" element={<CatalogPage />} /></Routes>; }

test("lists all tools including disabled", async () => {
  server.use(http.get("/admin/tools", () => HttpResponse.json(tools)));
  renderWithProviders(tree(), { route: "/admin/catalog" });
  expect(await screen.findByText("antifold")).toBeInTheDocument();
  expect(screen.getByText("ablang2")).toBeInTheDocument();
});

test("syncs the catalog and toasts the counts", async () => {
  server.use(
    http.get("/admin/tools", () => HttpResponse.json(tools)),
    http.post("/admin/catalog/sync", () => HttpResponse.json({ added: 2, updated: 1 })),
  );
  renderWithProviders(tree(), { route: "/admin/catalog" });
  await screen.findByText("antifold");
  await userEvent.click(screen.getByRole("button", { name: /sync/i }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/2 added/i)));
});
```

Run: `npm test -- "admin/CatalogPage"` → FAIL.

- [ ] **Step 2: Implement** hook + page; wire route (import as `AdminCatalogPage`).
- [ ] **Step 3: Run tests** → PASS; `npm run lint` + `npm run build`.
- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-admin-catalog.ts frontend/src/pages/admin/CatalogPage.tsx frontend/src/pages/admin/CatalogPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): admin catalog screen (toggle + sync)"
```

---

### Task 7: Runs oversight (list + detail)

**Files:**
- Create: `frontend/src/hooks/use-admin-runs.ts`, `frontend/src/pages/admin/AdminRunsPage.tsx`, `frontend/src/pages/admin/AdminRunDetailPage.tsx`, `frontend/src/pages/admin/AdminRunsPage.test.tsx`, `frontend/src/pages/admin/AdminRunDetailPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `adminListRuns`, `adminGetRun`, `adminCancelRun`, `adminArtifactUrl` (Task 1; hits the admin endpoint from Task 0), `isTerminal`; `AdminRunSummary`/`AdminRunRead`; `StatusBadge`; shadcn `Table`/`Select`/`AlertDialog`/`Button`; `toast`.
- Produces: `useAdminRuns(params)` (`['admin','runs', params]`), `useAdminRun(id)` (`['admin','run', id]`), `useAdminCancelRun()` (invalidate `['admin','runs']` + `['admin','run', id]`; toast); `<AdminRunsPage>` at `/admin/runs`, `<AdminRunDetailPage>` at `/admin/runs/:runId`.

**AdminRunsPage:** table of all runs (owner email via `run.user.email`, tool name+version, `StatusBadge`, created); a status `Select` filter (drives the `useAdminRuns({status})` param); rows link to `/admin/runs/:id`. States.
**AdminRunDetailPage:** `useAdminRun(runId)` (poll like 9a: `refetchInterval` stops at terminal); render owner (email), tool, status, timing, params, error, artifacts (download `<a href={adminArtifactUrl(runId, a.path)} download>` — the admin-scoped endpoint from Task 0, so downloads work for any user's run), and a Cancel action when `status==="queued"` → `AlertDialog` confirm → `useAdminCancelRun` (409 → toast). 404 → "not found".

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/admin/AdminRunsPage.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import AdminRunsPage from "@/pages/admin/AdminRunsPage";

const tool = { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" };
const user = { id: "u1", email: "alice@scripps.edu", display_name: "Alice" };
const runs = [{ id: "r1", tool, user, status: "queued", created_at: "2026-07-01T10:00:00Z", started_at: null, finished_at: null }];
function tree() { return <Routes><Route path="/admin/runs" element={<AdminRunsPage />} /></Routes>; }

test("lists all users' runs with owner", async () => {
  server.use(http.get("/admin/runs", () => HttpResponse.json(runs)));
  renderWithProviders(tree(), { route: "/admin/runs" });
  expect(await screen.findByText("alice@scripps.edu")).toBeInTheDocument();
  expect(screen.getByText("antifold")).toBeInTheDocument();
});
```

`frontend/src/pages/admin/AdminRunDetailPage.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import AdminRunDetailPage from "@/pages/admin/AdminRunDetailPage";

const tool = { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" };
const user = { id: "u1", email: "alice@scripps.edu", display_name: "Alice" };
const run = {
  id: "r1", tool, user, status: "succeeded", created_at: "2026-07-01T10:00:00Z",
  started_at: "2026-07-01T10:00:01Z", finished_at: "2026-07-01T10:01:00Z",
  params: { num_sequences: 2 }, assigned_gpu_ids: [0], wall_time_seconds: 59, gpu_seconds: 59,
  error: null, artifacts: [{ name: "result.txt", path: "raw/result.txt", size_bytes: 5, content_type: "text/plain" }],
};
function tree() { return <Routes><Route path="/admin/runs/:runId" element={<AdminRunDetailPage />} /></Routes>; }

test("renders owner, params, and an artifact link", async () => {
  server.use(http.get("/admin/runs/r1", () => HttpResponse.json(run)));
  renderWithProviders(tree(), { route: "/admin/runs/r1" });
  expect(await screen.findByText("alice@scripps.edu")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /result\.txt/i })).toHaveAttribute("href", "/admin/runs/r1/artifacts/raw/result.txt");
});

test("shows not-found for a missing run", async () => {
  server.use(http.get("/admin/runs/rX", () => HttpResponse.json({ detail: "Run not found" }, { status: 404 })));
  renderWithProviders(<Routes><Route path="/admin/runs/:runId" element={<AdminRunDetailPage />} /></Routes>, { route: "/admin/runs/rX" });
  expect(await screen.findByText(/not found/i)).toBeInTheDocument();
});
```

Run: `npm test -- AdminRuns AdminRunDetail` → FAIL.

- [ ] **Step 2: Implement** hook + both pages; wire routes.
- [ ] **Step 3: Run tests** → PASS; `npm run lint` + `npm run build`.
- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-admin-runs.ts "frontend/src/pages/admin/AdminRuns*.tsx" frontend/src/App.tsx
git commit -m "feat(frontend): admin job oversight (runs list + detail)"
```

---

### Task 8: Audit log screen + researcher toast retrofit + final gate

**Files:**
- Create: `frontend/src/hooks/use-admin-audit.ts`, `frontend/src/pages/admin/AuditLogPage.tsx`, `frontend/src/pages/admin/AuditLogPage.test.tsx`
- Modify: `frontend/src/hooks/use-runs.ts` (retrofit error toasts), `frontend/src/hooks/use-runs.test.ts` (or a new small test), `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `adminListAuditLogs`; `AuditLogRead`; shadcn `Table`; `toast`.
- Produces: `useAuditLogs(limit?)` (`['admin','audit']`); `<AuditLogPage>` at `/admin/audit`. Modifies `useCancelRun`/`useDeleteRun` to add `onError: (e) => toast.error(e instanceof ApiError ? e.detail : "…")`.

**AuditLogPage:** table (created_at, actor_id, action, target_type/target_id, details as compact JSON) newest-first from `useAuditLogs()`. States.

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/admin/AuditLogPage.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import AuditLogPage from "@/pages/admin/AuditLogPage";

const logs = [
  { id: "a1", actor_id: "u1", action: "user.update", target_type: "user", target_id: "u2", details: { tier: "power" }, created_at: "2026-07-01T10:00:00Z" },
];
function tree() { return <Routes><Route path="/admin/audit" element={<AuditLogPage />} /></Routes>; }

test("lists audit entries", async () => {
  server.use(http.get("/admin/audit-logs", () => HttpResponse.json(logs)));
  renderWithProviders(tree(), { route: "/admin/audit" });
  expect(await screen.findByText("user.update")).toBeInTheDocument();
});
```

Add to `frontend/src/hooks/use-runs.test.ts` (create if absent) a test that a failing cancel fires `toast.error`:

```tsx
import { http, HttpResponse } from "msw";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { createQueryClient } from "@/lib/query";
import { server } from "@/lib/test/server";
import { useCancelRun } from "@/hooks/use-runs";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));
import { toast } from "sonner";

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={createQueryClient()}>{children}</QueryClientProvider>;
}

test("cancel error surfaces a toast", async () => {
  server.use(http.post("/runs/r1/cancel", () => HttpResponse.json({ detail: "Only queued runs can be canceled" }, { status: 409 })));
  const { result } = renderHook(() => useCancelRun(), { wrapper });
  result.current.mutate("r1");
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/queued/i)));
});
```

Run: `npm test -- AuditLogPage use-runs` → FAIL.

- [ ] **Step 2: Implement** `use-admin-audit.ts` + `AuditLogPage.tsx`; wire `/admin/audit`. Retrofit `useCancelRun`/`useDeleteRun` in `use-runs.ts` with `onError` toasts (keep the existing `onSuccess` invalidations).
- [ ] **Step 3: Run tests** → PASS.
- [ ] **Step 4: Final gate**

Run: `npm run lint && npm test && npm run build`
Expected: eslint + prettier clean; whole suite green; `vite build` succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/use-admin-audit.ts frontend/src/pages/admin/AuditLogPage.tsx frontend/src/pages/admin/AuditLogPage.test.tsx frontend/src/hooks/use-runs.ts frontend/src/hooks/use-runs.test.ts frontend/src/App.tsx
git commit -m "feat(frontend): admin audit log + researcher cancel/delete error toasts"
```

---

## Self-Review notes (for the executor)

- **Spec coverage:** admin API client+types+proxy (T1) ✓; RequireAdmin guard + AdminLayout + routes + Toaster + table/alert-dialog primitives (T2) ✓; users incl. edit + password-reset token dialog (T3) ✓; allowlist add(+409)/remove-confirm (T4) ✓; settings (T5) ✓; catalog toggle+sync (T6) ✓; runs oversight list+detail+cancel (T7) ✓; audit log + researcher toast retrofit (T8) ✓. Toasts mounted (T2) and used on all mutations. No admin E2E (per decision).
- **Consistency:** query keys (`['admin', …]`), routes (`/admin/*`, index → `/admin/users`), api-fn names, and hook names are used identically across tasks. Audit API path is `/admin/audit-logs`; artifact download href uses the researcher `artifactUrl` (path `/runs/{id}/artifacts/{p}`) — the admin run detail links to the same artifact endpoint the backend serves.
- **Gotchas honored:** `/admin` added to the Vite proxy (T1); `table` + `alert-dialog` added, `sonner` `<Toaster/>` mounted (T2); admin `CatalogPage` lives under `pages/admin/` and is imported as `AdminCatalogPage` to avoid clashing with the researcher `pages/CatalogPage.tsx`.
- **Out of scope:** live RUNNING-job termination; sorting/pagination; admin E2E; the residual 9a polish items; Docker/static-serving (Plan 10).
- **Admin artifact download (closed):** Task 0 (backend) adds the admin-scoped `GET /admin/runs/{id}/artifacts/{path}` endpoint; the frontend uses `adminArtifactUrl` (Task 1) so admin run-detail downloads work for *any* user's run. (Implement Task 0 first — Task 7 consumes it.)
```
