# Frontend Researcher App (Plan 9a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the researcher-facing single-page app — the v1 core loop (authenticate → browse tools → guided schema-driven form → submit → watch status → download results) — as a thin client over the existing FastAPI JSON APIs.

**Architecture:** A Vite + React + TypeScript SPA in a new top-level `frontend/` package, same-origin with the FastAPI backend (dev via Vite proxy; prod static-serving is Plan 10). Server state is TanStack Query; forms are React Hook Form + Zod. The centerpiece is a schema-driven form engine that renders any autobio tool's JSON Schema into a guided form, so new tools need zero frontend work. The backend re-validates every submission, so client validation is a UX aid, not the gate.

**Tech Stack:** Vite, React, TypeScript (strict), Tailwind CSS, shadcn/ui, lucide-react, React Router, TanStack Query, React Hook Form, Zod, Vitest + Testing Library + userEvent + MSW, Playwright.

## Global Constraints

- **Vite + React + TypeScript (strict)**; no `any` — use `unknown` + narrowing. No `.js`/`.jsx`.
- **Tailwind + shadcn/ui + lucide-react**; `cn()` (clsx + tailwind-merge) for conditional classes.
- **React Router** for routing; **TanStack Query** for all server state; **React Hook Form + Zod** for forms.
- **Vitest + @testing-library/react + userEvent + MSW** (unit/component); **Playwright** (E2E). Query by role/label, not test IDs. Mock the API at the network level (MSW), not by stubbing `fetch`.
- Functional components only; `interface {ComponentName}Props`; files `PascalCase.tsx`; handlers `handle{Event}` / props `on{Event}`; semantic, accessible HTML (`<button>`, `<nav>`, `<main>`, labelled inputs).
- **ESLint** (typescript-eslint + react-hooks) + **Prettier**; **npm**; **Node 20+**.
- New top-level `frontend/` package (sibling to the Python `src/`).
- **Same-origin**: dev = Vite proxy of `/auth`, `/tools`, `/runs`, `/health` → `http://localhost:8000`; prod static-serving is Plan 10 (out of scope here).
- `npm run lint`, `npm test`, `npm run build` must all pass. All API calls use relative same-origin paths with `credentials: "include"`.

## Precision convention (read before executing)

- **Logic/contract code (Task 2 API client + types, Task 5 `buildZodSchema`) is given in full** — implement it as written.
- **For UI tasks (auth pages, catalog, submit, runs, run detail, shell), the Vitest test files given here ARE the behavioral contract — implement them verbatim (adapt only import paths if needed).** The component prose is a structural spec (what to render, which hooks/API calls, which states, exact props/signatures, which shadcn components). You may write the JSX yourself, but **every prop, signature, route path, and query key another task depends on must match this plan exactly.** Make the given tests pass.
- FastAPI error bodies are `{"detail": string}`; `ApiError.detail` carries that string.

## Backend API contract (client + all MSW mocks must match)

- `POST /auth/register` `{email,password,display_name}` → 201 `UserRead`; 403 (not allowlisted), 409 (already registered).
- `POST /auth/login` `{email,password}` → 200 `UserRead` (sets httpOnly cookie); 401 invalid; 403 with `detail` "Account is pending approval" or "Account is disabled".
- `POST /auth/logout` → 204. `GET /auth/me` → 200 `UserRead` / 401.
- `POST /auth/reset-password` `{token,new_password}` → 204; 400 invalid/expired.
- `GET /tools?category=` → `ToolSummary[]` (auth required). `GET /tools/{id}` → `ToolRead` / 404.
- `POST /runs` multipart(`tool_id`, `params`=JSON string, `files`=0+ File) → 201 `RunRead`; 422 (invalid params), 404 (unknown tool), 429 (quota).
- `GET /runs` → `RunSummary[]`. `GET /runs/{id}` → `RunRead` / 404.
- `POST /runs/{id}/cancel` → 200 `RunRead`; 404 / 409 (not cancelable). `DELETE /runs/{id}` → 204 / 404.
- `GET /runs/{id}/artifacts/{path}` → file stream (download link).

## Query keys & polling (keep identical everywhere)

- Keys: `['me']`, `['tools']` / `['tools', category]`, `['tool', id]`, `['runs']`, `['run', id]`.
- Mutations (`submitRun`, `cancelRun`, `deleteRun`) call `queryClient.invalidateQueries({ queryKey: ['runs'] })` (and `['run', id]` where relevant).
- Run detail poll: `refetchInterval: (q) => { const r = q.state.data; return r && isTerminal(r.status) ? false : 2500; }`.
- Runs list poll: `refetchInterval: (q) => (q.state.data ?? []).some((r) => !isTerminal(r.status)) ? 2500 : false`.

## File Structure

```
frontend/
  index.html
  package.json  vite.config.ts  tailwind.config.ts  postcss.config.js
  tsconfig.json  tsconfig.node.json  .eslintrc.cjs  .prettierrc  components.json
  playwright.config.ts
  src/
    main.tsx                      # React root: Router + QueryClientProvider
    App.tsx                       # route tree + <AppShell>
    index.css                     # tailwind directives + shadcn tokens
    vitest.setup.ts               # jest-dom + MSW server lifecycle
    types/api.ts                  # TS mirrors of backend schemas + JsonSchema + isTerminal
    lib/
      api.ts                      # typed fetch client + ApiError
      query.ts                    # QueryClient factory
      utils.ts                    # cn()
      test/                       # test-only helpers (renderWithProviders, msw handlers/server)
      schema-form/
        build-zod.ts              # JSON Schema (autobio subset) -> Zod
        SchemaForm.tsx            # renders a form from input_schema
        fields/                   # per-control widgets (FileField, JsonField, ...)
        __fixtures__/             # real captured autobio schemas
    components/
      ui/                         # shadcn primitives (generated into repo)
      AppShell.tsx  Sidebar.tsx  TopBar.tsx
      RequireAuth.tsx
      states/                     # Loading, ErrorState, EmptyState, StatusBadge
    hooks/
      use-auth.ts  use-tools.ts  use-runs.ts
    pages/
      LoginPage.tsx  RegisterPage.tsx  ResetPasswordPage.tsx
      CatalogPage.tsx  SubmitPage.tsx  RunsPage.tsx  RunDetailPage.tsx
  e2e/
    core-loop.spec.ts
```

---

### Task 1: Scaffold, toolchain, and CI

**Files:**
- Create: the whole `frontend/` scaffold (config files above), `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`, `frontend/src/lib/utils.ts`, `frontend/src/vitest.setup.ts`, `frontend/src/App.test.tsx`.
- Modify: `.github/workflows/ci.yml` (add a `frontend` job).

**Interfaces:**
- Produces: a runnable Vite app; `cn()` in `lib/utils.ts`; Vitest configured with jsdom + `vitest.setup.ts`; path alias `@` → `src`; npm scripts `dev`, `build`, `lint`, `test`, `test:e2e`, `preview`.

- [ ] **Step 1: Create the Vite React-TS app and install deps**

```bash
cd /home/briney/git/fold-at-scripps
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install @tanstack/react-query react-router-dom react-hook-form zod @hookform/resolvers clsx tailwind-merge lucide-react
npm install -D tailwindcss postcss autoprefixer vitest jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom msw @playwright/test prettier eslint-config-prettier
npx tailwindcss init -p
```

- [ ] **Step 2: Configure Tailwind, shadcn, TS alias, Vite proxy, Vitest**

- `tailwind.config.ts`: `content: ["./index.html", "./src/**/*.{ts,tsx}"]`; add a `primary` accent token under `theme.extend.colors` (a Scripps blue, e.g. `#0B5AA2`), and the shadcn CSS-variable color mappings. `darkMode: "class"`.
- `src/index.css`: `@tailwind base; @tailwind components; @tailwind utilities;` plus shadcn's CSS variables for light and `.dark`.
- `tsconfig.json`: `"strict": true`, and `"paths": { "@/*": ["./src/*"] }` with `"baseUrl": "."`.
- `vite.config.ts` (also holds the Vitest + alias + proxy config):

```ts
/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    proxy: {
      "/auth": "http://localhost:8000",
      "/tools": "http://localhost:8000",
      "/runs": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/vitest.setup.ts"],
    css: true,
    exclude: ["e2e/**", "node_modules/**"],
  },
});
```

- Initialize shadcn: `npx shadcn@latest init` (New York style, base color slate, CSS variables yes). Then add the primitives used across the app: `npx shadcn@latest add button input label select switch textarea card badge dialog sonner skeleton` (add others as tasks need them).
- `components.json` and `src/components/ui/*` are generated by shadcn — commit them.

- [ ] **Step 3: `lib/utils.ts`, `vitest.setup.ts`, npm scripts**

```ts
// src/lib/utils.ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

```ts
// src/vitest.setup.ts
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "@/lib/test/server";
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

`package.json` scripts: `"dev": "vite"`, `"build": "tsc -b && vite build"`, `"preview": "vite preview"`, `"lint": "eslint . && prettier --check ."`, `"test": "vitest run"`, `"test:e2e": "playwright test"`.

Create a minimal MSW server so the setup file imports resolve (handlers grow per task):

```ts
// src/lib/test/server.ts
import { setupServer } from "msw/node";
export const server = setupServer();
```

- [ ] **Step 4: Minimal App + smoke test**

`src/App.tsx` renders a `<main>` with an `<h1>fold@Scripps</h1>` for now (replaced in Task 3). `src/main.tsx` mounts `<App />` inside `<BrowserRouter>` + `<QueryClientProvider>` (client from Task 3 later; for now a local `new QueryClient()` is fine and will be refactored).

```tsx
// src/App.test.tsx
import { render, screen } from "@testing-library/react";
import App from "@/App";

test("renders the app heading", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /fold@scripps/i })).toBeInTheDocument();
});
```

- [ ] **Step 5: Run lint, test, build**

Run: `npm run lint && npm test && npm run build`
Expected: eslint + prettier clean; 1 test passes; `vite build` succeeds (emits `dist/`).

- [ ] **Step 6: Add frontend CI job**

In `.github/workflows/ci.yml`, add a second job (parallel to `test`):

```yaml
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm test
      - run: npm run build
```

- [ ] **Step 7: Commit**

```bash
git add frontend .github/workflows/ci.yml
git commit -m "feat(frontend): scaffold Vite React SPA + toolchain + CI"
```

---

### Task 2: API types + typed client

**Files:**
- Create: `frontend/src/types/api.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`, `frontend/src/lib/test/server.ts` (extend).

**Interfaces:**
- Produces (types): `UserRole`, `UserTier`, `UserStatus`, `RunStatus`, `UserRead`, `ToolSummary`, `ToolRead`, `ToolRef`, `ArtifactRead`, `RunSummary`, `RunRead`, `JsonSchema`, `isTerminal(s: RunStatus): boolean`.
- Produces (client): `ApiError`, and `getMe`, `login`, `register`, `logout`, `redeemPasswordReset`, `listTools`, `getTool`, `submitRun`, `listRuns`, `getRun`, `cancelRun`, `deleteRun`, `artifactUrl` — signatures exactly as below.

- [ ] **Step 1: Write the types**

```ts
// src/types/api.ts
export type UserRole = "user" | "admin";
export type UserTier = "standard" | "power";
export type UserStatus = "pending" | "active" | "disabled";
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

export interface UserRead {
  id: string; email: string; display_name: string;
  role: UserRole; tier: UserTier; status: UserStatus;
}
export interface ToolSummary {
  id: string; name: string; version: string; category: string;
  gpu_count: number; description: string | null; supports_batch: boolean;
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
  image_tag: string | null; default_timeout: number | null; input_schema: JsonSchema;
}
export interface ToolRef { id: string; name: string; version: string; category: string; }
export interface ArtifactRead {
  name: string; path: string; size_bytes: number | null; content_type: string | null;
}
export interface RunSummary {
  id: string; tool: ToolRef; status: RunStatus;
  created_at: string; started_at: string | null; finished_at: string | null;
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
```

- [ ] **Step 2: Write the failing client tests**

```ts
// src/lib/api.test.ts
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/lib/test/server";
import { ApiError, getMe, submitRun } from "@/lib/api";
import type { UserRead } from "@/types/api";

const user: UserRead = {
  id: "u1", email: "a@scripps.edu", display_name: "A",
  role: "user", tier: "standard", status: "active",
};

describe("api client", () => {
  it("returns typed JSON on success", async () => {
    server.use(http.get("/auth/me", () => HttpResponse.json(user)));
    await expect(getMe()).resolves.toEqual(user);
  });

  it("throws ApiError with detail on non-2xx", async () => {
    server.use(http.get("/auth/me", () => HttpResponse.json({ detail: "Not authenticated" }, { status: 401 })));
    await expect(getMe()).rejects.toMatchObject({ status: 401, detail: "Not authenticated" });
    await expect(getMe()).rejects.toBeInstanceOf(ApiError);
  });

  it("submitRun posts multipart with tool_id, params JSON, and files", async () => {
    let seen: { toolId: string | null; params: string | null; fileNames: string[] } | null = null;
    server.use(
      http.post("/runs", async ({ request }) => {
        const form = await request.formData();
        seen = {
          toolId: form.get("tool_id") as string | null,
          params: form.get("params") as string | null,
          fileNames: form.getAll("files").map((f) => (f as File).name),
        };
        return HttpResponse.json({ id: "r1" }, { status: 201 });
      }),
    );
    const file = new File(["ATOM"], "backbone.pdb", { type: "chemical/x-pdb" });
    await submitRun("t1", { structure_path: "backbone.pdb", num_sequences: 2 }, [file]);
    expect(seen).toEqual({
      toolId: "t1",
      params: JSON.stringify({ structure_path: "backbone.pdb", num_sequences: 2 }),
      fileNames: ["backbone.pdb"],
    });
  });
});
```

Run: `npm test -- api.test` → FAIL (module `@/lib/api` not found).

- [ ] **Step 3: Implement the client**

```ts
// src/lib/api.ts
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
```

- [ ] **Step 4: Run tests** → `npm test -- api.test` PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types frontend/src/lib/api.ts frontend/src/lib/api.test.ts
git commit -m "feat(frontend): typed API client + response types"
```

---

### Task 3: Query client, auth, app shell, and routes

**Files:**
- Create: `frontend/src/lib/query.ts`, `frontend/src/hooks/use-auth.ts`, `frontend/src/components/RequireAuth.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/components/Sidebar.tsx`, `frontend/src/components/TopBar.tsx`, `frontend/src/lib/test/render.tsx`, `frontend/src/components/RequireAuth.test.tsx`, `frontend/src/components/AppShell.test.tsx`.
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`.

**Interfaces:**
- Consumes: `getMe`, `logout` (Task 2); query keys.
- Produces: `createQueryClient()`; `useAuth(): { user: UserRead | undefined; isLoading: boolean; isError: boolean }` (query key `['me']`, `retry: false`); `<RequireAuth>` wrapper (renders children when `['me']` resolves; `<Navigate to="/login">` on error; a `role="status"` spinner while loading); `<AppShell>` (sidebar + top bar + `<Outlet/>`); test helper `renderWithProviders(ui, { route })`.

- [ ] **Step 1: Query client + test render helper**

```ts
// src/lib/query.ts
import { QueryClient } from "@tanstack/react-query";
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
}
```

```tsx
// src/lib/test/render.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";
import { createQueryClient } from "@/lib/query";

export function renderWithProviders(ui: ReactElement, opts: { route?: string } = {}): RenderResult {
  const client = createQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[opts.route ?? "/"]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}
```

- [ ] **Step 2: Write the failing tests**

```tsx
// src/components/RequireAuth.test.tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import RequireAuth from "@/components/RequireAuth";

const user = { id: "u1", email: "a@scripps.edu", display_name: "A", role: "user", tier: "standard", status: "active" };

function tree() {
  return (
    <Routes>
      <Route path="/login" element={<h1>Login</h1>} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<h1>Protected</h1>} />
      </Route>
    </Routes>
  );
}

test("renders protected content when authenticated", async () => {
  server.use(http.get("/auth/me", () => HttpResponse.json(user)));
  renderWithProviders(tree(), { route: "/" });
  expect(await screen.findByRole("heading", { name: /protected/i })).toBeInTheDocument();
});

test("redirects to /login when unauthenticated", async () => {
  server.use(http.get("/auth/me", () => HttpResponse.json({ detail: "Not authenticated" }, { status: 401 })));
  renderWithProviders(tree(), { route: "/" });
  await waitFor(() => expect(screen.getByRole("heading", { name: /login/i })).toBeInTheDocument());
});
```

```tsx
// src/components/AppShell.test.tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import AppShell from "@/components/AppShell";

const user = { id: "u1", email: "a@scripps.edu", display_name: "A", role: "user", tier: "standard", status: "active" };

test("shows Tools and Runs nav, hides Admin for non-admins", async () => {
  server.use(http.get("/auth/me", () => HttpResponse.json(user)));
  renderWithProviders(
    <Routes><Route element={<AppShell />}><Route path="/" element={<div />} /></Route></Routes>,
    { route: "/" },
  );
  expect(await screen.findByRole("link", { name: /tools/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /runs/i })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /admin/i })).not.toBeInTheDocument();
});
```

Run: `npm test -- RequireAuth AppShell` → FAIL (modules missing).

- [ ] **Step 3: Implement**

- `hooks/use-auth.ts`: `useQuery({ queryKey: ['me'], queryFn: getMe, retry: false })`, returning `{ user: data, isLoading, isError }`.
- `RequireAuth.tsx`: calls `useAuth()`; `isLoading` → a `<div role="status">` spinner; `isError` (401) → `<Navigate to="/login" replace state={{ from: location }} />`; else `<Outlet />`.
- `Sidebar.tsx`: a `<nav>` with React Router `<NavLink>`s to `/tools` ("Tools") and `/runs` ("Runs"); render an Admin `<NavLink to="/admin">` **only** when `useAuth().user?.role === "admin"` (target built in Plan 9b).
- `TopBar.tsx`: app title, a user menu (shadcn `DropdownMenu`) showing the email with a "Log out" item that calls `logout()` then `queryClient.setQueryData(['me'], null)`/invalidate + navigate to `/login`; a light/dark toggle that toggles `document.documentElement.classList` `dark`.
- `AppShell.tsx`: `<div>` layout with `<Sidebar/>` + `<TopBar/>` + `<main><Outlet/></main>`.
- `App.tsx`: the route tree —

```tsx
// public: /login, /register, /reset-password
// protected (element={<RequireAuth/>}) wrapping element={<AppShell/>}:
//   index -> <Navigate to="/tools"/>, /tools, /tools/:toolId, /runs, /runs/:runId
```

Use placeholder page components for now if Task 4/7+ pages don't yet exist (a `<h1>` each) so routing compiles; later tasks replace them.
- `main.tsx`: wrap `<App/>` in `<QueryClientProvider client={createQueryClient()}>` + `<BrowserRouter>`.

- [ ] **Step 4: Run tests** → `npm test` PASS (all suites). Then update `App.test.tsx` if the heading moved (the smoke test may target the login or shell heading now — keep one passing top-level render test).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/query.ts frontend/src/hooks/use-auth.ts frontend/src/components frontend/src/lib/test/render.tsx frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat(frontend): query client, auth guard, app shell, routes"
```

---

### Task 4: Auth pages (login, register, reset password)

**Files:**
- Create: `frontend/src/pages/LoginPage.tsx`, `RegisterPage.tsx`, `ResetPasswordPage.tsx`, and `frontend/src/pages/auth.test.tsx`.
- Modify: `frontend/src/App.tsx` (wire the real pages).

**Interfaces:**
- Consumes: `login`, `register`, `redeemPasswordReset`, `ApiError`; `useAuth`/`['me']`.
- Produces: three routed pages. Login on success invalidates `['me']` and navigates to `/` (or `location.state.from`). Register on success shows a "pending approval" confirmation. Reset page reads `?token=`, on 204 shows success + link to `/login`.

Each page: RHF + Zod, shadcn `Input`/`Label`/`Button`/`Card`; errors from `ApiError.detail` rendered in a `role="alert"` region; inputs have associated `<label>`s.

- [ ] **Step 1: Write the failing tests (the contract)**

```tsx
// src/pages/auth.test.tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";

const user = { id: "u1", email: "a@scripps.edu", display_name: "A", role: "user", tier: "standard", status: "active" };

function loginTree() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<h1>Home</h1>} />
    </Routes>
  );
}

test("login success navigates home", async () => {
  server.use(
    http.post("/auth/login", () => HttpResponse.json(user)),
    http.get("/auth/me", () => HttpResponse.json(user)),
  );
  renderWithProviders(loginTree(), { route: "/login" });
  await userEvent.type(screen.getByLabelText(/email/i), "a@scripps.edu");
  await userEvent.type(screen.getByLabelText(/password/i), "s3cret-pw");
  await userEvent.click(screen.getByRole("button", { name: /log in/i }));
  expect(await screen.findByRole("heading", { name: /home/i })).toBeInTheDocument();
});

test("login shows pending-approval message on 403", async () => {
  server.use(http.post("/auth/login", () => HttpResponse.json({ detail: "Account is pending approval" }, { status: 403 })));
  renderWithProviders(loginTree(), { route: "/login" });
  await userEvent.type(screen.getByLabelText(/email/i), "a@scripps.edu");
  await userEvent.type(screen.getByLabelText(/password/i), "s3cret-pw");
  await userEvent.click(screen.getByRole("button", { name: /log in/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/pending approval/i);
});

test("login shows invalid-credentials message on 401", async () => {
  server.use(http.post("/auth/login", () => HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 })));
  renderWithProviders(loginTree(), { route: "/login" });
  await userEvent.type(screen.getByLabelText(/email/i), "a@scripps.edu");
  await userEvent.type(screen.getByLabelText(/password/i), "wrong-pw-1");
  await userEvent.click(screen.getByRole("button", { name: /log in/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/invalid email or password/i);
});

test("register success shows pending confirmation", async () => {
  server.use(http.post("/auth/register", () => HttpResponse.json({ ...user, status: "pending" }, { status: 201 })));
  renderWithProviders(<Routes><Route path="/register" element={<RegisterPage />} /></Routes>, { route: "/register" });
  await userEvent.type(screen.getByLabelText(/email/i), "new@scripps.edu");
  await userEvent.type(screen.getByLabelText(/display name/i), "New");
  await userEvent.type(screen.getByLabelText(/password/i), "s3cret-pw");
  await userEvent.click(screen.getByRole("button", { name: /register/i }));
  expect(await screen.findByText(/pending approval/i)).toBeInTheDocument();
});

test("register shows 403 not-allowlisted message", async () => {
  server.use(http.post("/auth/register", () => HttpResponse.json({ detail: "not approved for registration" }, { status: 403 })));
  renderWithProviders(<Routes><Route path="/register" element={<RegisterPage />} /></Routes>, { route: "/register" });
  await userEvent.type(screen.getByLabelText(/email/i), "x@scripps.edu");
  await userEvent.type(screen.getByLabelText(/display name/i), "X");
  await userEvent.type(screen.getByLabelText(/password/i), "s3cret-pw");
  await userEvent.click(screen.getByRole("button", { name: /register/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/not approved/i);
});

test("reset password success then invalid", async () => {
  server.use(http.post("/auth/reset-password", () => new HttpResponse(null, { status: 204 })));
  renderWithProviders(<Routes><Route path="/reset-password" element={<ResetPasswordPage />} /></Routes>, { route: "/reset-password?token=abc" });
  await userEvent.type(screen.getByLabelText(/new password/i), "brand-new-pw-9");
  await userEvent.click(screen.getByRole("button", { name: /set password/i }));
  expect(await screen.findByText(/password updated/i)).toBeInTheDocument();

  server.use(http.post("/auth/reset-password", () => HttpResponse.json({ detail: "Invalid or expired reset token" }, { status: 400 })));
  renderWithProviders(<Routes><Route path="/reset-password" element={<ResetPasswordPage />} /></Routes>, { route: "/reset-password?token=bad" });
  await userEvent.type(screen.getByLabelText(/new password/i), "brand-new-pw-9");
  await userEvent.click(screen.getByRole("button", { name: /set password/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/invalid or expired/i);
});
```

Run: `npm test -- auth.test` → FAIL (pages missing).

- [ ] **Step 2: Implement the three pages** per the structural spec above (RHF + Zod; on mutation error, set an `ApiError.detail` string into an alert region; login uses `useMutation` then `queryClient.invalidateQueries(['me'])` + `navigate(from ?? "/")`; register toggles a "pending approval" success view; reset reads `useSearchParams().get("token")` and posts it with the new password, min length 8). Wire all three into `App.tsx` public routes.

- [ ] **Step 3: Run tests** → `npm test -- auth.test` PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx frontend/src/pages/RegisterPage.tsx frontend/src/pages/ResetPasswordPage.tsx frontend/src/pages/auth.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): auth pages (login, register, reset password)"
```

---

### Task 5: `buildZodSchema` + real schema fixtures

**Files:**
- Create: `frontend/src/lib/schema-form/build-zod.ts`, `frontend/src/lib/schema-form/build-zod.test.ts`, and fixtures under `frontend/src/lib/schema-form/__fixtures__/`.

**Interfaces:**
- Consumes: `JsonSchema` (Task 2).
- Produces: `buildZodSchema(schema: JsonSchema): z.ZodType` — a `z.object(...).passthrough()`; required→non-optional, others optional; `string`(+`enum`→`z.enum`, else `z.string`), `integer`→`z.number().int()` (+min/max), `number`→`z.number()` (+min/max), `boolean`→`z.boolean`, scalar `array`→`z.array(item)`, `anyOf:[T,null]`→`T.nullable()`, everything else (objects, arrays-of-objects, `additionalProperties`)→`z.unknown()`.

- [ ] **Step 1: Capture real autobio schemas as fixtures**

```bash
cd /home/briney/git/fold-at-scripps
mkdir -p frontend/src/lib/schema-form/__fixtures__
for t in antifold ablang2 boltz2; do
  autobio info "$t" --format json | python -c "import sys,json;print(json.dumps(json.load(sys.stdin)['input_schema'],indent=2))" \
    > "frontend/src/lib/schema-form/__fixtures__/$t.json"
done
```

(These are real: antifold has `structure_path` string+`format:path`, `num_sequences` integer default, `temperature` number default, `chains_to_design` `anyOf:[array,null]`, `fixed_positions` object, `extra` object; ablang2 has required `sequences` array + `anyOf:[T,null]` scalars + `extra`; boltz2 has `sequences` object, `num_models` integer default, `templates` `anyOf:[array,null]`.)

- [ ] **Step 2: Write the failing tests**

```ts
// src/lib/schema-form/build-zod.test.ts
import { describe, expect, it } from "vitest";
import { buildZodSchema } from "@/lib/schema-form/build-zod";
import type { JsonSchema } from "@/types/api";
import antifold from "./__fixtures__/antifold.json";
import ablang2 from "./__fixtures__/ablang2.json";

describe("buildZodSchema on real autobio schemas", () => {
  it("validates a correct antifold payload (file field as filename string)", () => {
    const schema = buildZodSchema(antifold as JsonSchema);
    expect(schema.safeParse({ structure_path: "b.pdb", num_sequences: 2, temperature: 0.1 }).success).toBe(true);
  });
  it("rejects an antifold payload missing the required structure_path", () => {
    const schema = buildZodSchema(antifold as JsonSchema);
    expect(schema.safeParse({ num_sequences: 2 }).success).toBe(false);
  });
  it("coerces/accepts anyOf:[T,null] fields as nullable/optional (ablang2 layer)", () => {
    const schema = buildZodSchema(ablang2 as JsonSchema);
    expect(schema.safeParse({ sequences: ["EVQ"], layer: null }).success).toBe(true);
    expect(schema.safeParse({ sequences: ["EVQ"] }).success).toBe(true);
  });
  it("requires ablang2 sequences (a scalar array)", () => {
    const schema = buildZodSchema(ablang2 as JsonSchema);
    expect(schema.safeParse({}).success).toBe(false);
    expect(schema.safeParse({ sequences: "notarray" }).success).toBe(false);
  });
});

describe("buildZodSchema field-kind mapping (inline schemas for enum/boolean)", () => {
  it("maps enum -> restricted string set", () => {
    const s = buildZodSchema({ type: "object", required: ["mode"], properties: { mode: { type: "string", enum: ["fast", "slow"] } } });
    expect(s.safeParse({ mode: "fast" }).success).toBe(true);
    expect(s.safeParse({ mode: "nope" }).success).toBe(false);
  });
  it("maps boolean and integer(min) correctly", () => {
    const s = buildZodSchema({ type: "object", properties: { flag: { type: "boolean" }, n: { type: "integer", minimum: 1 } } });
    expect(s.safeParse({ flag: true, n: 3 }).success).toBe(true);
    expect(s.safeParse({ n: 0 }).success).toBe(false);
    expect(s.safeParse({ n: 1.5 }).success).toBe(false);
  });
});
```

Ensure `tsconfig.json` has `"resolveJsonModule": true`. Run: `npm test -- build-zod` → FAIL (module missing).

- [ ] **Step 3: Implement `build-zod.ts`**

```ts
import { z } from "zod";
import type { JsonSchema } from "@/types/api";

function unwrapNullable(schema: JsonSchema): { inner: JsonSchema; nullable: boolean } {
  if (Array.isArray(schema.anyOf)) {
    const nonNull = schema.anyOf.filter((s) => s.type !== "null");
    const nullable = schema.anyOf.some((s) => s.type === "null");
    if (nonNull.length === 1) return { inner: nonNull[0], nullable };
  }
  return { inner: schema, nullable: false };
}

function isScalar(schema: JsonSchema): boolean {
  return (
    schema.type === "string" || schema.type === "integer" ||
    schema.type === "number" || schema.type === "boolean"
  );
}

function fieldZod(schema: JsonSchema): z.ZodTypeAny {
  const { inner, nullable } = unwrapNullable(schema);
  let base: z.ZodTypeAny;
  if (Array.isArray(inner.enum) && inner.enum.length > 0) {
    base = z.enum(inner.enum.map(String) as [string, ...string[]]);
  } else if (inner.type === "string") {
    base = z.string();
  } else if (inner.type === "integer" || inner.type === "number") {
    let num = z.number();
    if (inner.type === "integer") num = num.int();
    if (typeof inner.minimum === "number") num = num.min(inner.minimum);
    if (typeof inner.maximum === "number") num = num.max(inner.maximum);
    base = num;
  } else if (inner.type === "boolean") {
    base = z.boolean();
  } else if (inner.type === "array" && inner.items && isScalar(inner.items)) {
    base = z.array(fieldZod(inner.items));
  } else {
    base = z.unknown(); // objects, arrays-of-objects, additionalProperties: server-validated
  }
  return nullable ? base.nullable() : base;
}

export function buildZodSchema(schema: JsonSchema): z.ZodType {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const [key, prop] of Object.entries(properties)) {
    const field = fieldZod(prop);
    shape[key] = required.has(key) ? field : field.optional();
  }
  return z.object(shape).passthrough();
}
```

- [ ] **Step 4: Run tests** → `npm test -- build-zod` PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/schema-form/build-zod.ts frontend/src/lib/schema-form/build-zod.test.ts frontend/src/lib/schema-form/__fixtures__ frontend/tsconfig.json
git commit -m "feat(frontend): JSON-Schema-to-Zod builder with real autobio fixtures"
```

---

### Task 6: `SchemaForm` + field widgets

**Files:**
- Create: `frontend/src/lib/schema-form/SchemaForm.tsx`, `frontend/src/lib/schema-form/fields/FileField.tsx`, `frontend/src/lib/schema-form/fields/JsonField.tsx`, `frontend/src/lib/schema-form/SchemaForm.test.tsx`.

**Interfaces:**
- Consumes: `buildZodSchema` (Task 5); `ToolRead`, `JsonSchema` (Task 2); shadcn `Input/Select/Switch/Textarea/Button/Label`.
- Produces: `interface SchemaFormProps { tool: ToolRead; onSubmit: (data: { values: Record<string, unknown>; files: File[] }) => void; submitting?: boolean }` and `export default function SchemaForm(props): JSX.Element`.

**Field mapping (top-level `properties`):** `string`+`enum`→`Select`; `string`+`format:"path"`→`<FileField>` (stores the `File`, sets `values[name] = file.name`); plain `string`→`Input` (long/`description` mentions multi-line → `Textarea`); `integer`/`number`→`Input type="number"` (register with `valueAsNumber`); `boolean`→`Switch`; scalar `array`→repeatable text rows; **object or array-of-objects or `additionalProperties` (incl. `extra`, boltz2 `sequences`, antifold `fixed_positions`)→`<JsonField>`** (a `Textarea` whose string is `JSON.parse`d on change; parse failure sets a field error). **Guided/advanced:** fields that are required AND scalar render up top; everything optional/defaulted/complex renders inside an "Advanced options" `<details>`/shadcn collapsible. Labels/help from `title`/`description`; required marked with `*`.

**Submit:** collect RHF values; pull `File`s from the file fields into a `files: File[]`; call `onSubmit({ values, files })` (the SubmitPage builds the request via `submitRun`).

- [ ] **Step 1: Write the failing tests (contract)**

```tsx
// src/lib/schema-form/SchemaForm.test.tsx
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@testing-library/react";
import { vi } from "vitest";
import SchemaForm from "@/lib/schema-form/SchemaForm";
import type { ToolRead } from "@/types/api";
import antifold from "./__fixtures__/antifold.json";

function tool(): ToolRead {
  return {
    id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding",
    gpu_count: 1, description: "d", supports_batch: false,
    image_tag: "antifold:1", default_timeout: 600, input_schema: antifold as ToolRead["input_schema"],
  };
}

test("renders required structure_path up top and hides advanced fields until expanded", () => {
  render(<SchemaForm tool={tool()} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText(/structure path/i)).toBeInTheDocument();
  // num_sequences is optional/defaulted -> inside Advanced, not visible initially
  expect(screen.queryByLabelText(/num sequences/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /advanced options/i })).toBeInTheDocument();
});

test("uploads a file and submits values + files", async () => {
  const onSubmit = vi.fn();
  render(<SchemaForm tool={tool()} onSubmit={onSubmit} />);
  const file = new File(["ATOM"], "backbone.pdb", { type: "chemical/x-pdb" });
  await userEvent.upload(screen.getByLabelText(/structure path/i), file);
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(onSubmit).toHaveBeenCalledTimes(1);
  const arg = onSubmit.mock.calls[0][0];
  expect(arg.files.map((f: File) => f.name)).toEqual(["backbone.pdb"]);
  expect(arg.values.structure_path).toBe("backbone.pdb");
});

test("an object field renders a JSON editor and rejects invalid JSON", async () => {
  const onSubmit = vi.fn();
  render(<SchemaForm tool={tool()} onSubmit={onSubmit} />);
  await userEvent.click(screen.getByRole("button", { name: /advanced options/i }));
  const jsonEditor = screen.getByLabelText(/fixed positions/i);
  await userEvent.type(jsonEditor, "{not json");
  await userEvent.upload(screen.getByLabelText(/structure path/i), new File(["A"], "b.pdb"));
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(onSubmit).not.toHaveBeenCalled();
  expect(await screen.findByText(/valid json/i)).toBeInTheDocument();
});
```

Run: `npm test -- SchemaForm` → FAIL (modules missing).

- [ ] **Step 2: Implement `FileField`, `JsonField`, and `SchemaForm`** per the mapping spec. Use `useForm({ resolver: zodResolver(buildZodSchema(tool.input_schema)), defaultValues })` with defaults seeded from schema `default`s. `FileField` renders an `<input type="file">` with an associated `<label>` (label text from `title` or the humanized key); on change it stores the File in a ref/state map and `setValue(name, file.name)`. `JsonField` renders a labelled `<Textarea>`; it registers a synthetic value and, on submit, validates `JSON.parse`; on failure calls `setError(name, { message: "Enter valid JSON" })`. Group required+scalar vs advanced as specified.

- [ ] **Step 3: Run tests** → `npm test -- SchemaForm` PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/schema-form/SchemaForm.tsx frontend/src/lib/schema-form/fields frontend/src/lib/schema-form/SchemaForm.test.tsx
git commit -m "feat(frontend): schema-driven form renderer + field widgets"
```

---

### Task 7: Catalog page + shared state components

**Files:**
- Create: `frontend/src/hooks/use-tools.ts`, `frontend/src/components/states/Loading.tsx`, `ErrorState.tsx`, `EmptyState.tsx`, `StatusBadge.tsx`, `frontend/src/pages/CatalogPage.tsx`, `frontend/src/pages/CatalogPage.test.tsx`.
- Modify: `frontend/src/App.tsx` (wire `/tools`).

**Interfaces:**
- Consumes: `listTools` (`['tools']`); `ToolSummary`; `RunStatus` (for `StatusBadge`, reused by Tasks 9/10).
- Produces: `useTools()` → `useQuery({ queryKey: ['tools'], queryFn: () => listTools() })`; `<Loading>` (`role="status"`), `<ErrorState onRetry>` (`role="alert"` + retry button), `<EmptyState>`, `<StatusBadge status: RunStatus>` (colored shadcn `Badge`); `<CatalogPage>` at `/tools`.

**CatalogPage:** fetch tools; a text `<input>` (labelled "Search tools") filters by name/description; group results by `category` (section headers), each tool a shadcn `Card` (name, version, `description`, `gpu_count`, `supports_batch` chip) that is a link/navigates to `/tools/:id`. Loading → `<Loading>`; error → `<ErrorState>`; empty (no tools or no matches) → `<EmptyState>`.

- [ ] **Step 1: Write the failing tests**

```tsx
// src/pages/CatalogPage.test.tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import CatalogPage from "@/pages/CatalogPage";

const tools = [
  { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding", gpu_count: 1, description: "inverse folding", supports_batch: false },
  { id: "t2", name: "ablang2", version: "1.0.0", category: "embedding", gpu_count: 1, description: "embeddings", supports_batch: true },
];

function tree() {
  return (
    <Routes>
      <Route path="/tools" element={<CatalogPage />} />
      <Route path="/tools/:toolId" element={<h1>Submit</h1>} />
    </Routes>
  );
}

test("lists tools grouped by category and filters", async () => {
  server.use(http.get("/tools", () => HttpResponse.json(tools)));
  renderWithProviders(tree(), { route: "/tools" });
  expect(await screen.findByText("antifold")).toBeInTheDocument();
  expect(screen.getByText("ablang2")).toBeInTheDocument();
  expect(screen.getByText(/inverse-folding/i)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText(/search tools/i), "ablang");
  expect(screen.queryByText("antifold")).not.toBeInTheDocument();
  expect(screen.getByText("ablang2")).toBeInTheDocument();
});

test("navigates to submit on card click", async () => {
  server.use(http.get("/tools", () => HttpResponse.json(tools)));
  renderWithProviders(tree(), { route: "/tools" });
  await userEvent.click(await screen.findByRole("link", { name: /antifold/i }));
  expect(await screen.findByRole("heading", { name: /submit/i })).toBeInTheDocument();
});

test("shows empty state when no tools", async () => {
  server.use(http.get("/tools", () => HttpResponse.json([])));
  renderWithProviders(tree(), { route: "/tools" });
  expect(await screen.findByText(/no tools/i)).toBeInTheDocument();
});

test("shows error state on failure", async () => {
  server.use(http.get("/tools", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
  renderWithProviders(tree(), { route: "/tools" });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
```

Run: `npm test -- CatalogPage` → FAIL.

- [ ] **Step 2: Implement** the state components, `use-tools`, and `CatalogPage` per spec; wire `/tools`.

- [ ] **Step 3: Run tests** → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-tools.ts frontend/src/components/states frontend/src/pages/CatalogPage.tsx frontend/src/pages/CatalogPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): tool catalog page + shared state components"
```

---

### Task 8: Submit page

**Files:**
- Create: `frontend/src/pages/SubmitPage.tsx`, `frontend/src/pages/SubmitPage.test.tsx`.
- Modify: `frontend/src/App.tsx` (wire `/tools/:toolId`).

**Interfaces:**
- Consumes: `getTool` (`['tool', id]`), `submitRun`, `ApiError`, `SchemaForm`, `isTerminal` n/a; `useNavigate`, `useParams`.
- Produces: `<SubmitPage>` at `/tools/:toolId`.

**SubmitPage:** read `:toolId`; `useQuery(['tool', toolId], () => getTool(toolId))`; loading/error states. Render `<SchemaForm tool onSubmit>`; the handler calls `useMutation` → `submitRun(tool.id, values, files)`, `onSuccess: (run) => { invalidate ['runs']; navigate('/runs/' + run.id) }`. Map `ApiError`: 422 → inline "Invalid parameters: {detail}"; 429 → inline "Quota reached: {detail}"; other → generic alert. Show a submitting state (disable submit).

- [ ] **Step 1: Write the failing tests**

```tsx
// src/pages/SubmitPage.test.tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import SubmitPage from "@/pages/SubmitPage";
import antifold from "@/lib/schema-form/__fixtures__/antifold.json";

const tool = { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding", gpu_count: 1, description: "d", supports_batch: false, image_tag: "antifold:1", default_timeout: 600, input_schema: antifold };

function tree() {
  return (
    <Routes>
      <Route path="/tools/:toolId" element={<SubmitPage />} />
      <Route path="/runs/:runId" element={<h1>Run Detail</h1>} />
    </Routes>
  );
}

test("submits and navigates to the new run", async () => {
  server.use(
    http.get("/tools/t1", () => HttpResponse.json(tool)),
    http.post("/runs", () => HttpResponse.json({ id: "r1", tool: { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" }, status: "queued", created_at: "", started_at: null, finished_at: null }, { status: 201 })),
  );
  renderWithProviders(tree(), { route: "/tools/t1" });
  await userEvent.upload(await screen.findByLabelText(/structure path/i), new File(["A"], "b.pdb"));
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(await screen.findByRole("heading", { name: /run detail/i })).toBeInTheDocument();
});

test("shows quota message on 429", async () => {
  server.use(
    http.get("/tools/t1", () => HttpResponse.json(tool)),
    http.post("/runs", () => HttpResponse.json({ detail: "Concurrency limit of 3 reached" }, { status: 429 })),
  );
  renderWithProviders(tree(), { route: "/tools/t1" });
  await userEvent.upload(await screen.findByLabelText(/structure path/i), new File(["A"], "b.pdb"));
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/quota|limit/i);
});
```

Run: `npm test -- SubmitPage` → FAIL.

- [ ] **Step 2: Implement** `SubmitPage` per spec; wire the route.
- [ ] **Step 3: Run tests** → PASS.
- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/SubmitPage.tsx frontend/src/pages/SubmitPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): run submission page (schema form + multipart submit)"
```

---

### Task 9: Runs list page

**Files:**
- Create: `frontend/src/hooks/use-runs.ts`, `frontend/src/pages/RunsPage.tsx`, `frontend/src/pages/RunsPage.test.tsx`.
- Modify: `frontend/src/App.tsx` (wire `/runs`).

**Interfaces:**
- Consumes: `listRuns`, `cancelRun`, `deleteRun`, `isTerminal`, `StatusBadge`.
- Produces: `useRuns()` → `useQuery({ queryKey: ['runs'], queryFn: listRuns, refetchInterval: (q) => (q.state.data ?? []).some((r) => !isTerminal(r.status)) ? 2500 : false })`; `useCancelRun()`, `useDeleteRun()` mutations that `invalidateQueries(['runs'])`; `<RunsPage>` at `/runs`.

**RunsPage:** table/list of runs newest-first (`created_at` desc), each row: tool name+version, `<StatusBadge>`, created time, and a link to `/runs/:id`; a "Cancel" button shown only when `status === "queued"`; a "Delete" (hide) button. Loading/error/empty states.

- [ ] **Step 1: Write the failing tests**

```tsx
// src/pages/RunsPage.test.tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import RunsPage from "@/pages/RunsPage";

const ref = { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" };
const runs = [
  { id: "r1", tool: ref, status: "queued", created_at: "2026-07-01T10:00:00Z", started_at: null, finished_at: null },
  { id: "r2", tool: ref, status: "succeeded", created_at: "2026-07-01T09:00:00Z", started_at: null, finished_at: null },
];

test("lists runs with status and cancels a queued run", async () => {
  server.use(
    http.get("/runs", () => HttpResponse.json(runs)),
    http.post("/runs/r1/cancel", () => HttpResponse.json({ ...runs[0], status: "canceled" })),
  );
  renderWithProviders(<Routes><Route path="/runs" element={<RunsPage />} /></Routes>, { route: "/runs" });
  expect(await screen.findByText(/queued/i)).toBeInTheDocument();
  expect(screen.getByText(/succeeded/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
  await waitFor(() => expect(screen.getByText(/canceled/i)).toBeInTheDocument());
});

test("shows empty state with no runs", async () => {
  server.use(http.get("/runs", () => HttpResponse.json([])));
  renderWithProviders(<Routes><Route path="/runs" element={<RunsPage />} /></Routes>, { route: "/runs" });
  expect(await screen.findByText(/no runs/i)).toBeInTheDocument();
});
```

Run: `npm test -- RunsPage` → FAIL.

- [ ] **Step 2: Implement** `use-runs`, `RunsPage`; wire `/runs`. After cancel, the mutation invalidates `['runs']`; the cancel test's second GET should reflect the canceled status — set the MSW `GET /runs` handler to return the updated status after the cancel call (or return canceled from the start of the refetch). Keep the handler stateful or override on refetch.
- [ ] **Step 3: Run tests** → PASS.
- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-runs.ts frontend/src/pages/RunsPage.tsx frontend/src/pages/RunsPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): runs list page with polling + cancel/delete"
```

---

### Task 10: Run detail page

**Files:**
- Create: `frontend/src/pages/RunDetailPage.tsx`, `frontend/src/pages/RunDetailPage.test.tsx`.
- Modify: `frontend/src/App.tsx` (wire `/runs/:runId`).

**Interfaces:**
- Consumes: `getRun` (`['run', id]` with detail polling), `cancelRun`, `artifactUrl`, `isTerminal`, `StatusBadge`.
- Produces: `<RunDetailPage>` at `/runs/:runId`.

**RunDetailPage:** `useQuery(['run', runId], () => getRun(runId), { refetchInterval: (q) => { const r = q.state.data; return r && isTerminal(r.status) ? false : 2500; } })`. Render: `<StatusBadge>`, tool name+version, timing (created/started/finished, wall/gpu seconds when present), submitted `params` (as a `<dl>` or formatted JSON), `error` (in a `role="alert"` when `status === "failed"`), and an **Artifacts** section listing each `artifact` with a download `<a href={artifactUrl(runId, artifact.path)} download>` (name + human size). A "Cancel" button when `status === "queued"`. Reserve an empty, clearly-labelled "Visualization (coming soon)" region (documents the deferred feature; renders nothing functional). Loading/error/404 states.

- [ ] **Step 1: Write the failing tests**

```tsx
// src/pages/RunDetailPage.test.tsx
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import RunDetailPage from "@/pages/RunDetailPage";

const ref = { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" };
const succeeded = {
  id: "r1", tool: ref, status: "succeeded", created_at: "2026-07-01T10:00:00Z",
  started_at: "2026-07-01T10:00:01Z", finished_at: "2026-07-01T10:01:00Z",
  params: { structure_path: "b.pdb", num_sequences: 2 }, assigned_gpu_ids: [0],
  wall_time_seconds: 59, gpu_seconds: 59, error: null,
  artifacts: [{ name: "result.txt", path: "raw/result.txt", size_bytes: 5, content_type: "text/plain" }],
};

function tree() {
  return <Routes><Route path="/runs/:runId" element={<RunDetailPage />} /></Routes>;
}

test("renders status, params, and a downloadable artifact link", async () => {
  server.use(http.get("/runs/r1", () => HttpResponse.json(succeeded)));
  renderWithProviders(tree(), { route: "/runs/r1" });
  expect(await screen.findByText(/succeeded/i)).toBeInTheDocument();
  expect(screen.getByText(/num_sequences/i)).toBeInTheDocument();
  const link = screen.getByRole("link", { name: /result\.txt/i });
  expect(link).toHaveAttribute("href", "/runs/r1/artifacts/raw/result.txt");
});

test("shows the error message for a failed run", async () => {
  server.use(http.get("/runs/r1", () => HttpResponse.json({ ...succeeded, status: "failed", artifacts: [], error: "autobio run failed" })));
  renderWithProviders(tree(), { route: "/runs/r1" });
  expect(await screen.findByRole("alert")).toHaveTextContent(/autobio run failed/i);
});

test("shows not-found for a missing run", async () => {
  server.use(http.get("/runs/rX", () => HttpResponse.json({ detail: "Run not found" }, { status: 404 })));
  renderWithProviders(<Routes><Route path="/runs/:runId" element={<RunDetailPage />} /></Routes>, { route: "/runs/rX" });
  expect(await screen.findByText(/not found/i)).toBeInTheDocument();
});
```

Run: `npm test -- RunDetailPage` → FAIL.

- [ ] **Step 2: Implement** `RunDetailPage` per spec; wire `/runs/:runId`.
- [ ] **Step 3: Run tests** → PASS.
- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/RunDetailPage.tsx frontend/src/pages/RunDetailPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): run detail page with polling + artifact downloads"
```

---

### Task 11: End-to-end core loop (Playwright)

**Files:**
- Create: `frontend/playwright.config.ts`, `frontend/e2e/core-loop.spec.ts`.
- Modify: `frontend/package.json` (ensure `test:e2e`), `.github/workflows/ci.yml` (optional E2E step).

**Interfaces:**
- Consumes: the built/served SPA. Uses Playwright `page.route(...)` to stub all `**/auth/**`, `**/tools/**`, `**/runs/**` responses (no live backend), driving the full researcher loop deterministically.

- [ ] **Step 1: Playwright config**

```ts
// playwright.config.ts
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:4173" },
  webServer: { command: "npm run build && npm run preview -- --port 4173", port: 4173, reuseExistingServer: !process.env.CI },
});
```

- [ ] **Step 2: Write the E2E spec (stubbed API)**

`e2e/core-loop.spec.ts`: a single test that stubs, via `page.route`:
- `GET /auth/me` → 200 active user;
- `GET /tools` → `[antifold summary]`; `GET /tools/t1` → antifold `ToolRead` (inline schema with `structure_path` + `num_sequences`);
- `POST /runs` → 201 `{ id: "r1", status: "queued", ... }`;
- `GET /runs/r1` → first call `queued`, subsequent calls `succeeded` with one artifact (use a counter in the route handler);
- `GET /runs/r1/artifacts/raw/result.txt` → 200 body "HELLO".

Steps: `goto("/tools")` → click antifold → upload a file into "Structure Path" → click Submit → expect the run detail heading + a "queued" badge → wait for the "succeeded" badge (polling) → assert the `result.txt` download link points at `/runs/r1/artifacts/raw/result.txt`.

- [ ] **Step 3: Install browsers and run**

Run: `npx playwright install --with-deps chromium && npm run test:e2e`
Expected: the core-loop spec passes.

- [ ] **Step 4: Whole-suite gate**

Run: `npm run lint && npm test && npm run build`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e frontend/package.json .github/workflows/ci.yml
git commit -m "test(frontend): Playwright core-loop E2E"
```

---

## Self-Review notes (for the executor)

- **Spec coverage:** scaffold+CI (T1) ✓; typed client (T2) ✓; auth+guard+shell+routing (T3) ✓; auth pages incl. pending/disabled/reset (T4) ✓; schema→Zod (T5) ✓; schema-driven form incl. file upload + guided/advanced + JSON editor (T6) ✓; catalog (T7) ✓; submit w/ 422/429 (T8) ✓; runs list + polling + cancel/delete (T9) ✓; run detail + artifacts + polling + reserved viz region (T10) ✓; E2E core loop (T11) ✓. Same-origin/no-CORS is inherent in the relative-path client + Vite proxy; production static-serving is deferred to Plan 10 (noted, not built).
- **Consistency:** query keys (`['me']`,`['tools']`,`['tool',id]`,`['runs']`,`['run',id]`), routes (`/login`,`/register`,`/reset-password`,`/tools`,`/tools/:toolId`,`/runs`,`/runs/:runId`), and the `submitRun(toolId, params, files)` / `SchemaForm onSubmit({values,files})` contracts are used identically across tasks.
- **Out of scope:** admin console (Plan 9b), in-browser viz, run organization, OpenAPI codegen, SSE. Do not build them.
</content>
