# fold@Scripps Frontend — Researcher App (Plan 9a) — Design

> Design spec for the researcher-facing single-page app: the shared frontend
> foundation plus the v1 core loop (authenticate → browse tools → guided form →
> submit → watch status → download results). The admin console is a separate
> follow-up (Plan 9b) built on the same foundation.

## Purpose & scope

Build the browser front-end that makes autobio's tools usable by any researcher,
per the vision's v1 core loop. This is a thin client over the existing FastAPI
JSON APIs (`/auth`, `/tools`, `/runs`); it holds no domain logic. It must be
**guided by default, advanced on demand**, and — critically — **schema-driven**,
so integrating a new autobio tool requires no frontend changes.

**In scope (9a):** project scaffold, typed API client + server-state layer,
authentication + routing + app shell, tool catalog, the schema-driven submit
form with file uploads, run list / run detail / artifact download, status
polling, and the test suite.

**Out of scope:**
- **Admin console → Plan 9b** (users, allowlist, settings, catalog admin, job
  oversight, audit log), built on this foundation.
- **Deferred by the vision (leave room, don't build):** in-browser result
  visualization (3D structure viewers, sequence/score plots), run
  organization/projects, side-by-side comparison.
- **Plan 10 owns:** serving the built assets from FastAPI in production and the
  Docker/build wiring.

## Stack

- **Vite + React + TypeScript (strict).** Pure SPA (no SSR/Next.js) — this
  overrides `WEB.md`'s Next.js default per the project's `ARCHITECTURE.md`
  decision (SPA against a FastAPI JSON backend).
- **Tailwind CSS + shadcn/ui + lucide-react**; `cn()` (clsx + tailwind-merge).
- **React Router** for client routing.
- **TanStack Query** for all server state (polling, cache invalidation,
  loading/error states).
- **React Hook Form + Zod** for forms and client-side validation.
- **Vitest + @testing-library/react + userEvent + MSW** (unit/component);
  **Playwright** (E2E).

All other `WEB.md` conventions apply: functional components only,
`interface {Component}Props`, `PascalCase.tsx`, `handle*`/`on*` handler naming,
avoid `any` (use `unknown` + narrowing), Tailwind utilities in JSX (extract a
component when a pattern repeats 3+ times), semantic/accessible HTML, and
`type`-vs-`interface` per the guide.

## Serving & environments

**Same-origin** everywhere, so the httpOnly session cookie works with zero CORS:

- **Development:** the Vite dev server proxies the API path prefixes
  (`/auth`, `/tools`, `/runs`, `/health`, and later `/admin`) to the FastAPI dev
  server (`http://localhost:8000`). The frontend calls same-origin relative
  paths; no API base-URL config, no CORS.
- **Production:** FastAPI serves the built `frontend/dist/` as static assets with
  an SPA fallback to `index.html` for unknown non-API routes. The exact
  StaticFiles/fallback wiring and Dockerfile build stage are **Plan 10's**
  responsibility; this plan only assumes same-origin relative API calls.

## Project structure

A new top-level `frontend/` package (sibling to the Python `src/`):

```
frontend/
  index.html
  package.json  vite.config.ts  tailwind.config.ts  tsconfig.json
  src/
    main.tsx            # bootstraps React + Router + QueryClientProvider
    App.tsx             # route tree + app shell
    lib/
      api.ts            # typed fetch wrapper + ApiError
      query.ts          # QueryClient config
      utils.ts          # cn()
      schema-form/      # the schema-driven form engine (see below)
        build-zod.ts    # JSON Schema (autobio subset) -> Zod
        SchemaForm.tsx  # renders a form from input_schema
        fields/         # per-control field widgets
    components/
      ui/               # shadcn primitives (generated into the repo)
      AppShell.tsx  Sidebar.tsx  TopBar.tsx
      RequireAuth.tsx
      states/           # Loading, ErrorState, EmptyState, StatusBadge
    pages/
      LoginPage.tsx  RegisterPage.tsx  ResetPasswordPage.tsx
      CatalogPage.tsx  SubmitPage.tsx
      RunsPage.tsx  RunDetailPage.tsx
    hooks/
      use-auth.ts  use-tools.ts  use-runs.ts
    types/
      api.ts            # TS mirrors of backend response schemas
```

## Data layer & API client

- **`api.ts`** — a thin `fetch` wrapper: same-origin relative paths,
  `credentials: "include"`, JSON by default and `multipart/form-data` for run
  submission. Non-2xx responses throw a typed `ApiError { status, detail }`
  (parsed from FastAPI's `{"detail": ...}`). Small typed functions per endpoint:
  `getMe`, `login`, `register`, `logout`, `redeemPasswordReset`, `listTools`,
  `getTool`, `submitRun`, `listRuns`, `getRun`, `cancelRun`, `deleteRun`, and an
  artifact-download URL helper.
- **Server state (TanStack Query).** Query keys: `['me']`, `['tools']`
  (optionally `['tools', category]`), `['tool', id]`, `['runs']`, `['run', id]`.
  Mutations (`submitRun`, `cancelRun`, `deleteRun`) invalidate `['runs']` (and the
  affected `['run', id]`).
- **Polling.** Run detail: `useQuery(['run', id], …, { refetchInterval: r =>
  isTerminal(r.status) ? false : 2500 })`. The run list polls on a similar
  interval while any listed run is non-terminal, then stops. `isTerminal` =
  status in {succeeded, failed, canceled}.
- **Types (`types/api.ts`).** Hand-written TS interfaces mirroring the backend
  Pydantic response models: `UserRead`, `ToolSummary`/`ToolRead`,
  `RunSummary`/`RunRead`, `ArtifactRead`, and the `RunStatus` union. Kept in
  sync by hand for now (small surface); OpenAPI codegen is a noted future option.

## Authentication, routing & app shell

- **Bootstrap.** On load, `useQuery(['me'], getMe)` determines the session.
  `useAuth()` exposes `{ user, isLoading }`. A 401 means unauthenticated.
- **Routes.**
  - Public: `/login`, `/register`, `/reset-password` (reads `?token=`).
  - Guarded by `RequireAuth`: `/` (→ `/tools`), `/tools`, `/tools/:toolId`,
    `/runs`, `/runs/:runId`.
- **`RequireAuth`.** If `['me']` resolves to a user → render; if 401 → redirect
  to `/login`, preserving the intended path; while loading → a full-page spinner.
- **Auth flows.** Login posts credentials, then refetches `['me']`. The backend
  returns 403 with a specific detail for **pending** ("Account is pending
  approval") vs **disabled** accounts — surface that message on the login screen.
  Register is allowlist-gated (403 if not allowed, 409 if already registered) and
  results in a pending account; show a "pending approval" confirmation.
  `/reset-password` posts `{token, new_password}` → 204 (public redemption from
  Plan 8); 400 shows "invalid or expired".
- **App shell.** Left sidebar (Tools, Runs; an Admin link appears only when
  `user.role === "admin"`, wired in 9b), top bar (app name, user menu → logout,
  light/dark toggle). Clean neutral shadcn theme with a single Scripps-accent
  color token; light + dark via the class strategy.

## Schema-driven form engine (core)

Two independently-testable units under `lib/schema-form/`. The backend
re-validates every submission against the tool's JSON Schema, so **client
validation is a UX nicety, not the gate** — the engine degrades permissively on
anything it doesn't recognize and lets the server be authoritative.

### `build-zod.ts` — `buildZodSchema(inputSchema) -> ZodType`
Maps the autobio JSON-Schema subset (Pydantic-generated) to a Zod schema for the
RHF resolver:

- `object` + `properties` → `z.object`; `required` → non-optional; everything
  else optional (respecting `default`).
- `string` → `z.string`; with `enum` → `z.enum`; with `format: "path"` → treated
  as a file field (validated as "a file selected or an existing string value").
- `integer` / `number` → `z.number` (`z.number().int()` for integer), honoring
  `minimum`/`maximum` when present and `default`.
- `boolean` → `z.boolean` (default false).
- `array` (of a scalar item type) → `z.array(item)`.
- Nullable via `anyOf: [T, null]` (e.g. `chains_to_design`) → `T.nullable()`.
- `extra` / `additionalProperties: true` object → optional
  `z.record(z.unknown())` (advanced passthrough).
- Unknown/unsupported shapes → `z.unknown()` (permissive; server validates).

### `SchemaForm.tsx` — `<SchemaForm tool={ToolRead} onSubmit={…}>`
- An RHF form using `zodResolver(buildZodSchema(tool.input_schema))`, defaults
  seeded from schema `default`s.
- Iterates top-level `properties`, rendering each via a `fields/` widget chosen
  by type/`format`:
  - enum → `Select`; boolean → `Switch`; number/integer → numeric `Input`;
    plain string → `Input` (or `Textarea` for long/multiline); array → repeatable
    rows; `format: "path"` → a file **dropzone** widget; `extra` → an "advanced
    (tool-specific)" key/value or JSON editor.
  - Labels/help text come from schema `title`/`description`; required fields
    marked.
- **Guided vs advanced:** required and non-defaulted fields render up top;
  optional/defaulted fields collapse under an "Advanced options" disclosure.
- **File fields:** the dropzone holds the selected `File` object(s) and sets the
  corresponding `params[field]` to the filename, matching the Plan 7 convention
  (the backend resolves `format:"path"` params to the staged file's path).
- **Submission** builds the exact Plan 7 `POST /runs` `multipart/form-data`:
  `tool_id`, `params` (JSON string of the non-file field values + file
  filenames), and each selected `File` appended under `files`.

## Screens & states

Every data view explicitly handles **loading / error / empty**; shared
`states/` components (`Loading`, `ErrorState` with retry, `EmptyState`,
`StatusBadge`) keep this uniform.

- **Catalog — `/tools`.** Enabled tools (`GET /tools`) grouped by category, with
  a text filter. Each card shows name, version, description, `gpu_count`,
  `supports_batch`; clicking navigates to submit.
- **Submit — `/tools/:toolId`.** Fetch tool detail (`GET /tools/{id}` incl.
  `input_schema`), render `<SchemaForm>`. On submit → `POST /runs` → navigate to
  the new run's detail. Surface 422 (validation) and 429 (quota) inline.
- **Runs — `/runs`.** The user's runs (`GET /runs`), newest first, with status
  badges; polls while any run is active. Row → detail. Per-row actions: cancel
  (queued only; `POST /runs/{id}/cancel`) and delete/hide
  (`DELETE /runs/{id}`), each invalidating `['runs']`.
- **Run detail — `/runs/:runId`.** Status, timing (created/started/finished,
  wall/gpu seconds), submitted params, error message (if failed), and the
  artifacts list with download links (`GET /runs/{id}/artifacts/{path}`). Polls
  until terminal. Cancel action when queued. A reserved, empty "visualization"
  region documents the deferred viz feature without building it.

## Error handling

- `ApiError` carries the HTTP status + FastAPI `detail`; components map it to
  friendly inline messages (422 field/validation, 429 quota, 403 auth-state,
  404 not-found, 5xx generic "something went wrong, retry").
- A top-level React error boundary catches render errors with a recoverable
  fallback.
- 401 from any query (session expired/lost) routes back to `/login`.

## Testing

- **Unit (Vitest).** The schema engine is the priority: `buildZodSchema` and the
  `SchemaForm` field mapping are tested against **real captured autobio schemas**
  (fixtures, e.g. antifold/esm_if1/an embedding tool) covering each field kind
  (string, enum, number, boolean, array, `format:path`, nullable `anyOf`,
  `extra`). Assert that `<SchemaForm>` builds the correct multipart body on
  submit (tool_id, params JSON, files).
- **Component (Vitest + Testing Library + MSW).** Auth guard/redirect, catalog
  states, run list polling/actions, run detail states — querying by role/label,
  mocking the API at the network level with MSW.
- **E2E (Playwright).** The core loop against MSW-backed or a real dev backend:
  log in → pick a tool → fill the guided form (incl. a file upload) → submit →
  see the queued run → (status advances) → download an artifact.

## Success criteria

- A researcher with no CLI/Docker/GPU knowledge can log in, pick any enabled
  autobio tool, complete its guided form (with sensible defaults and file
  uploads), submit, watch it progress, and download results — entirely in the
  browser.
- Adding a new autobio tool requires **zero** frontend changes (schema-driven).
- All views handle loading/error/empty; the schema engine is covered by tests
  over real autobio schemas; the core-loop E2E passes.
- Same-origin session-cookie auth works with no CORS; unauthenticated access
  redirects to login; pending/disabled accounts get clear messaging.

## Deferred / future (explicitly not built here)

- Admin console (Plan 9b). In-browser 3D/plot visualization; run
  organization/projects; side-by-side comparison. OpenAPI-generated types.
  SSE/WebSocket status streaming (polling suffices now). Production static
  serving + Docker (Plan 10).
