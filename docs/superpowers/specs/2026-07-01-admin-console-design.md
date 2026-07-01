# fold@Scripps Frontend — Admin Console (Plan 9b) — Design

> Design spec for the admin console: the management UI for the couple of admins,
> built on the already-shipped Plan 9a frontend foundation and consuming the
> Plan 8 `/admin/*` (and public `/auth/reset-password`) APIs. This is a focused
> extension — it reuses 9a's architecture wholesale and adds an admin-only area.

## Purpose & scope

Give admins a browser UI for the operations the Plan 8 backend already exposes:
manage users, the registration allowlist, system settings, the tool catalog,
job oversight across all users, and the audit log. It is a thin client over the
`/admin/*` JSON APIs; no domain logic lives in the frontend.

**In scope (9b):** an `/admin` area gated to admins, the six admin screens
(users, allowlist, settings, catalog, runs oversight, audit log), the admin API
client functions + types + query hooks, app-wide toast notifications, and a
small retrofit wiring toasts into the researcher cancel/delete mutations.

**Out of scope / deferred:**
- Live termination of RUNNING jobs (the backend defers this; admin cancel is
  QUEUED-only, matching Plan 8).
- Sorting/pagination beyond simple in-render filtering (small scale — a handful
  of users, bounded runs).
- An admin Playwright E2E (component + guard tests suffice; add later only if
  hands-on testing shows gaps).
- Other 9a polish items (theme persistence, redirect query/hash, a11y
  `aria-describedby`, code-split) unless trivially folded; Plan 10 owns
  Docker/static-serving.

## Foundation reused from 9a (unchanged)

Vite + React + TS(strict) SPA under `frontend/`; Tailwind + shadcn/ui +
lucide-react + `cn()`; React Router; TanStack Query; React Hook Form + Zod;
Vitest + Testing Library + MSW. Same-origin cookie auth. Existing pieces reused
directly: `lib/api.ts` (`request`/`ApiError`), `hooks/use-auth.ts`
(`useAuth`, query key `['me']`), `components/RequireAuth.tsx`,
`components/AppShell.tsx`/`Sidebar.tsx`/`TopBar.tsx` (the sidebar already shows
an admin link for `role === "admin"`), `components/states/*`
(`Loading`/`ErrorState`/`EmptyState`/`StatusBadge`), `lib/test/render.tsx`,
`lib/schema-form/*` (available if a settings/edit form benefits, though admin
edit forms are small and hand-built). Global conventions from 9a apply
verbatim: TS strict / no `any`, functional components, `interface {X}Props`,
query by role/label in tests, **no `instanceof File`/`Blob`**, ESLint + Prettier
clean, shadcn primitives added non-interactively (`npx shadcn@latest add -y`).

## Architecture: routing, guard, toasts

- **`RequireAdmin` guard** (`components/RequireAdmin.tsx`): nests *inside* the
  authenticated area; uses `useAuth()`; while loading → the shared spinner; if
  no user → (RequireAuth already handles this) ; if `user.role !== "admin"` →
  `<Navigate to="/" replace />` (redirect non-admins away). Else `<Outlet/>`.
- **`/admin` area** under `RequireAuth` → `RequireAdmin` → an **`AdminLayout`**
  (`pages/admin/AdminLayout.tsx`) that renders a secondary tab-nav (NavLinks:
  Users, Allowlist, Settings, Catalog, Runs, Audit) + `<Outlet/>`, all within
  the existing `AppShell`. Routes: `/admin` (index → `/admin/users`),
  `/admin/users`, `/admin/allowed-emails`, `/admin/settings`, `/admin/catalog`,
  `/admin/runs`, `/admin/runs/:runId`, `/admin/audit`.
- **Toasts:** mount sonner `<Toaster/>` once (in `App`/`main`). Admin mutations
  fire `toast.success(...)` / `toast.error(err instanceof ApiError ? err.detail
  : "Something went wrong")`. Retrofit the researcher `useCancelRun`/
  `useDeleteRun` (9a) with `onError` toasts (they are currently silent on
  failure — the one 9a gap this plan closes).

## API/data layer

- **Types (`types/api.ts`, extend):** mirror the Plan 8 response schemas —
  `AdminUserRead` (id, email, display_name, role, tier, status,
  max_concurrent_runs_override, created_at), `AdminUserUpdate` (all optional:
  status/tier/max_concurrent_runs_override), `AllowedEmailRead` (id, email,
  created_at), `SystemSettingsRead` (maintenance_mode,
  standard_max_concurrent_runs, power_max_concurrent_runs, updated_at) +
  `SystemSettingsUpdate` (all optional), `ToolAdminRead` (id, name, version,
  category, enabled, gpu_count, description, image_tag, default_timeout,
  supports_batch), `CatalogSyncResult` (added, updated), `UserRef` (id, email,
  display_name), `AdminRunSummary` (id, tool: ToolRef, user: UserRef, status,
  created_at, started_at, finished_at), `AdminRunRead` (AdminRunSummary + params,
  assigned_gpu_ids, wall_time_seconds, gpu_seconds, error, artifacts),
  `AuditLogRead` (id, actor_id, action, target_type, target_id, details,
  created_at), `PasswordResetResponse` (token, expires_at). Reuse existing
  `RunStatus`/`UserRole`/`UserTier`/`UserStatus`/`ToolRef`/`ArtifactRead`.
- **Client (`lib/api.ts`, extend):** `adminListUsers()`, `adminGetUser(id)`,
  `adminUpdateUser(id, changes)`, `adminCreatePasswordReset(id)`,
  `adminListAllowedEmails()`, `adminAddAllowedEmail(email)`,
  `adminRemoveAllowedEmail(id)`, `adminGetSettings()`,
  `adminUpdateSettings(changes)`, `adminListTools()`,
  `adminSetToolEnabled(id, enabled)`, `adminSyncCatalog()`,
  `adminListRuns({ userId?, status? })`, `adminGetRun(id)`,
  `adminCancelRun(id)`, `adminListAuditLogs(limit?)`. All reuse the existing
  `request<T>` helper (same-origin, `credentials:"include"`, `ApiError`).
- **Hooks:** admin query/mutation hooks with keys namespaced under `['admin',
  …]` (`['admin','users']`, `['admin','allowed-emails']`, `['admin','settings']`,
  `['admin','tools']`, `['admin','runs', filters]`, `['admin','run', id]`,
  `['admin','audit']`). Mutations invalidate the relevant admin key and toast.

## Screens

Every list handles loading / error / empty via the shared `states/`
components. Tables are shadcn `Table`; filtering is computed in render (the 9a
catalog pattern). Destructive actions use a shadcn `AlertDialog` confirm.

- **Users — `/admin/users`.** Table: email, display_name, role, tier, status
  (badge), quota override. Filter by email/status. Row actions: **Edit** (a
  shadcn `Dialog` with a small form to set status/tier/max_concurrent_runs_
  override → `adminUpdateUser`), and **Reset password** (→ `adminCreatePassword
  Reset` → a `Dialog` displaying the one-time token with a copy button and a
  "shown once — convey it to the user out of band" warning).
- **Allowlist — `/admin/allowed-emails`.** Table: email, created_at. An
  "Add email" input (→ `adminAddAllowedEmail`; 409 → toast "already allowed").
  Remove per row (`AlertDialog` confirm → `adminRemoveAllowedEmail`).
- **Settings — `/admin/settings`.** A form: `maintenance_mode` switch,
  `standard_max_concurrent_runs`, `power_max_concurrent_runs` (numbers, ≥0) →
  `adminUpdateSettings` (partial). Toast on save.
- **Catalog — `/admin/catalog`.** Table of **all** tools (incl. disabled):
  name, version, category, enabled toggle (`adminSetToolEnabled`). A "Sync
  catalog" button (`adminSyncCatalog` → toast "N added, M updated"). Filter by
  name.
- **Runs oversight — `/admin/runs`.** Table of **all** users' runs: owner email,
  tool name+version, status (badge), created. Filter by status (and optionally
  user). Row → `/admin/runs/:runId`. **Run detail** (`/admin/runs/:runId`):
  owner, tool, status, timing, params, error, artifacts (download links via
  `artifactUrl`), and a Cancel action when `status === "queued"` (`AlertDialog`
  confirm → `adminCancelRun`, 409 → toast). May reuse presentation pieces from
  the 9a `RunDetailPage` but is a distinct admin view (shows the owner).
- **Audit log — `/admin/audit`.** Table: created_at, actor (id), action,
  target_type/target_id, details (compact/JSON), newest-first; a limit control
  (default 100).

## Error handling

`ApiError.detail` drives toast/inline messages (403 shouldn't occur inside the
guard; 404 → "not found"; 409 → conflict message; 422 → validation; 5xx →
generic). A non-admin who reaches `/admin` is redirected by `RequireAdmin`. A
session lost mid-session (401 from any admin query) routes back to `/login` via
the existing 9a behavior.

## Testing

Vitest + Testing Library + `userEvent` + MSW, querying by role/label:
- **`RequireAdmin`** guard: admin renders children; non-admin (role `user`) is
  redirected; loading shows the spinner.
- Per screen: list renders (grouped/filtered where applicable), empty + error
  states, and the key mutation path drives an MSW-mocked request → cache
  invalidation → a visible toast (assert the toast text) and/or updated row.
  Users: edit dialog updates a user; reset-password dialog shows the returned
  token. Allowlist: add (+409) / remove. Settings: save. Catalog: toggle + sync.
  Runs: list + filter + cancel (409). Audit: list.
- A test asserting the researcher `useCancelRun`/`useDeleteRun` retrofit surfaces
  an error toast on failure.
- No new Playwright E2E (per decision).

## Success criteria

- An admin can, entirely in the browser: review/activate/suspend users, change
  tier/quota, issue a password-reset token, manage the allowlist, edit system
  settings, enable/disable tools and trigger a catalog sync, oversee and cancel
  any user's queued run, and read the audit log.
- Non-admins cannot reach `/admin` (guard redirect); the console reuses the 9a
  foundation with no architectural divergence.
- Every mutation gives toast feedback; all lists handle loading/error/empty;
  `npm run lint`, `npm test`, `npm run build` stay green (CI unchanged:
  lint+test+build).

## Deferred / future (explicitly not built here)

Live RUNNING-job termination; table sorting/pagination; admin E2E; the residual
9a polish items; production static-serving + Docker (Plan 10).
