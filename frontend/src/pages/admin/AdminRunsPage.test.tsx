import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import AdminRunsPage from "@/pages/admin/AdminRunsPage";

const tool = { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" };
const user = { id: "u1", email: "alice@scripps.edu", display_name: "Alice" };
const runs = [
  {
    id: "r1",
    tool,
    user,
    status: "queued",
    created_at: "2026-07-01T10:00:00Z",
    started_at: null,
    finished_at: null,
  },
];
function tree() {
  return (
    <Routes>
      <Route path="/admin/runs" element={<AdminRunsPage />} />
    </Routes>
  );
}

test("lists all users' runs with owner", async () => {
  server.use(http.get("/admin/runs", () => HttpResponse.json(runs)));
  renderWithProviders(tree(), { route: "/admin/runs" });
  expect(await screen.findByText("alice@scripps.edu")).toBeInTheDocument();
  expect(screen.getByText("antifold")).toBeInTheDocument();
});
