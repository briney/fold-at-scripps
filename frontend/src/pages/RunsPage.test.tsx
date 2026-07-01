import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import RunsPage from "@/pages/RunsPage";

const ref = { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" };
const runs = [
  {
    id: "r1",
    tool: ref,
    status: "queued",
    created_at: "2026-07-01T10:00:00Z",
    started_at: null,
    finished_at: null,
  },
  {
    id: "r2",
    tool: ref,
    status: "succeeded",
    created_at: "2026-07-01T09:00:00Z",
    started_at: null,
    finished_at: null,
  },
];

function tree() {
  return (
    <Routes>
      <Route path="/runs" element={<RunsPage />} />
      <Route path="/runs/:runId" element={<h1>Run Detail</h1>} />
    </Routes>
  );
}

test("lists runs with status and cancels a queued run", async () => {
  // Stateful GET handler: after the cancel POST flips r1, the invalidation-driven
  // refetch returns the canceled status.
  let r1Status = "queued";
  server.use(
    http.get("/runs", () => HttpResponse.json([{ ...runs[0], status: r1Status }, runs[1]])),
    http.post("/runs/r1/cancel", () => {
      r1Status = "canceled";
      return HttpResponse.json({ ...runs[0], status: "canceled" });
    }),
  );
  renderWithProviders(tree(), { route: "/runs" });

  expect(await screen.findByText(/queued/i)).toBeInTheDocument();
  expect(screen.getByText(/succeeded/i)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

  await waitFor(() => expect(screen.getByText(/canceled/i)).toBeInTheDocument());
});

test("shows empty state with no runs", async () => {
  server.use(http.get("/runs", () => HttpResponse.json([])));
  renderWithProviders(tree(), { route: "/runs" });

  expect(await screen.findByText(/no runs/i)).toBeInTheDocument();
});
