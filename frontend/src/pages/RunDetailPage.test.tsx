import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";

import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import RunDetailPage from "@/pages/RunDetailPage";

const ref = { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" };
const succeeded = {
  id: "r1",
  tool: ref,
  status: "succeeded",
  created_at: "2026-07-01T10:00:00Z",
  started_at: "2026-07-01T10:00:01Z",
  finished_at: "2026-07-01T10:01:00Z",
  params: { structure_path: "b.pdb", num_sequences: 2 },
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
      <Route path="/runs/:runId" element={<RunDetailPage />} />
    </Routes>
  );
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
  server.use(
    http.get("/runs/r1", () =>
      HttpResponse.json({
        ...succeeded,
        status: "failed",
        artifacts: [],
        error: "autobio run failed",
      }),
    ),
  );
  renderWithProviders(tree(), { route: "/runs/r1" });
  expect(await screen.findByRole("alert")).toHaveTextContent(/autobio run failed/i);
});

test("shows not-found for a missing run", async () => {
  server.use(
    http.get("/runs/rX", () => HttpResponse.json({ detail: "Run not found" }, { status: 404 })),
  );
  renderWithProviders(
    <Routes>
      <Route path="/runs/:runId" element={<RunDetailPage />} />
    </Routes>,
    { route: "/runs/rX" },
  );
  expect(await screen.findByText(/not found/i)).toBeInTheDocument();
});
