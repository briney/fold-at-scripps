import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import AdminRunDetailPage from "@/pages/admin/AdminRunDetailPage";

const tool = { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" };
const user = { id: "u1", email: "alice@scripps.edu", display_name: "Alice" };
const run = {
  id: "r1",
  tool,
  user,
  status: "succeeded",
  created_at: "2026-07-01T10:00:00Z",
  started_at: "2026-07-01T10:00:01Z",
  finished_at: "2026-07-01T10:01:00Z",
  params: { num_sequences: 2 },
  assigned_gpu_ids: [0],
  wall_time_seconds: 59,
  gpu_seconds: 59,
  error: null,
  artifacts: [
    { name: "result.txt", path: "raw/result.txt", size_bytes: 5, content_type: "text/plain" },
  ],
};
function tree() {
  return (
    <Routes>
      <Route path="/admin/runs/:runId" element={<AdminRunDetailPage />} />
    </Routes>
  );
}

test("renders owner, params, and an artifact link", async () => {
  server.use(http.get("/admin/runs/r1", () => HttpResponse.json(run)));
  renderWithProviders(tree(), { route: "/admin/runs/r1" });
  expect(await screen.findByText("alice@scripps.edu")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /result\.txt/i })).toHaveAttribute(
    "href",
    "/admin/runs/r1/artifacts/raw/result.txt",
  );
});

test("shows not-found for a missing run", async () => {
  server.use(
    http.get("/admin/runs/rX", () =>
      HttpResponse.json({ detail: "Run not found" }, { status: 404 }),
    ),
  );
  renderWithProviders(
    <Routes>
      <Route path="/admin/runs/:runId" element={<AdminRunDetailPage />} />
    </Routes>,
    { route: "/admin/runs/rX" },
  );
  expect(await screen.findByText(/not found/i)).toBeInTheDocument();
});
