import { expect, test, type Route } from "@playwright/test";

/**
 * End-to-end "core loop" for the researcher app, driven entirely against
 * stubbed API responses (no live backend). Exercises: authenticated shell →
 * catalog → submit form (with file upload) → run detail → polling to a
 * terminal status → artifact download link.
 */

const ACTIVE_USER = {
  id: "u1",
  email: "researcher@scripps.edu",
  display_name: "Test Researcher",
  role: "user",
  tier: "standard",
  status: "active",
};

const ANTIFOLD_SUMMARY = {
  id: "t1",
  name: "AntiFold",
  version: "1.0.0",
  category: "design",
  gpu_count: 1,
  description: "Inverse folding for antibody sequence design.",
  supports_batch: false,
};

const ANTIFOLD_TOOL = {
  ...ANTIFOLD_SUMMARY,
  image_tag: "antifold:1.0.0",
  default_timeout: 3600,
  input_schema: {
    type: "object",
    required: ["structure_path"],
    properties: {
      structure_path: {
        type: "string",
        format: "path",
        title: "Structure Path",
        description: "Input structure file (PDB/CIF).",
      },
      num_sequences: {
        type: "integer",
        title: "Num Sequences",
        default: 10,
      },
    },
  },
};

const CREATED_AT = "2026-06-30T12:00:00Z";

const QUEUED_RUN = {
  id: "r1",
  tool: {
    id: "t1",
    name: "AntiFold",
    version: "1.0.0",
    category: "design",
  },
  status: "queued",
  created_at: CREATED_AT,
  started_at: null,
  finished_at: null,
};

const SUCCEEDED_RUN = {
  ...QUEUED_RUN,
  status: "succeeded",
  started_at: "2026-06-30T12:00:05Z",
  finished_at: "2026-06-30T12:00:30Z",
  params: { structure_path: "input.pdb", num_sequences: 10 },
  assigned_gpu_ids: [0],
  wall_time_seconds: 25,
  gpu_seconds: 25,
  error: null,
  artifacts: [
    {
      name: "result.txt",
      path: "raw/result.txt",
      size_bytes: 5,
      content_type: "text/plain",
    },
  ],
};

const QUEUED_RUN_DETAIL = {
  ...QUEUED_RUN,
  params: { structure_path: "input.pdb", num_sequences: 10 },
  assigned_gpu_ids: null,
  wall_time_seconds: null,
  gpu_seconds: null,
  error: null,
  artifacts: [],
};

function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/**
 * The app is a client-routed SPA whose paths (`/tools`, `/runs/...`) collide
 * with the API paths it fetches. Only intercept API calls (fetch/xhr); let
 * document navigations fall through so `vite preview` serves `index.html`.
 */
function isApiCall(route: Route): boolean {
  return route.request().resourceType() === "fetch";
}

test("researcher core loop: catalog → submit → run succeeds → download", async ({ page }) => {
  // Auth: the route guard reads GET /auth/me.
  await page.route("**/auth/me", (route) => fulfillJson(route, ACTIVE_USER));

  // Tool catalog + detail.
  await page.route("**/tools/t1", (route) =>
    isApiCall(route) ? fulfillJson(route, ANTIFOLD_TOOL) : route.continue(),
  );
  await page.route("**/tools", (route) =>
    isApiCall(route) ? fulfillJson(route, [ANTIFOLD_SUMMARY]) : route.continue(),
  );

  // Submit: POST /runs returns a queued run.
  await page.route("**/runs", async (route) => {
    if (!isApiCall(route)) {
      await route.continue();
      return;
    }
    if (route.request().method() === "POST") {
      await fulfillJson(route, QUEUED_RUN, 201);
      return;
    }
    await fulfillJson(route, [QUEUED_RUN]);
  });

  // Run detail polling: first poll queued, subsequent polls succeeded.
  let runPolls = 0;
  await page.route("**/runs/r1", async (route) => {
    if (!isApiCall(route)) {
      await route.continue();
      return;
    }
    runPolls += 1;
    await fulfillJson(route, runPolls === 1 ? QUEUED_RUN_DETAIL : SUCCEEDED_RUN);
  });

  // Artifact download.
  await page.route("**/runs/r1/artifacts/raw/result.txt", (route) =>
    route.fulfill({ status: 200, contentType: "text/plain", body: "HELLO" }),
  );

  // 1. Land on the catalog. Navigate to the app root (served as index.html by
  // `vite preview`) and let client-side routing redirect `/` → `/tools`.
  await page.goto("/");
  await expect(page).toHaveURL(/\/tools$/);
  await expect(page.getByRole("heading", { name: "Tools", level: 1 })).toBeVisible();

  // 2. Open the AntiFold tool.
  await page.getByRole("link", { name: /AntiFold/ }).click();
  await expect(page.getByRole("heading", { name: "AntiFold", level: 1 })).toBeVisible();

  // 3. Upload a structure file.
  await page.getByLabel("Structure Path").setInputFiles({
    name: "input.pdb",
    mimeType: "chemical/x-pdb",
    buffer: Buffer.from("ATOM  test\n"),
  });

  // 4. Submit the run.
  await page.getByRole("button", { name: "Submit" }).click();

  // 5. Land on run detail with a queued badge.
  await expect(page).toHaveURL(/\/runs\/r1$/);
  await expect(page.getByText("queued")).toBeVisible();

  // 6. Wait for polling to reach the succeeded status.
  await expect(page.getByText("succeeded")).toBeVisible();

  // 7. The artifact download link points at the raw artifact route.
  const download = page.getByRole("link", { name: "result.txt" });
  await expect(download).toHaveAttribute("href", "/runs/r1/artifacts/raw/result.txt");
});
