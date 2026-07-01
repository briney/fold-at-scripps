import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import AuditLogPage from "@/pages/admin/AuditLogPage";

const logs = [
  {
    id: "a1",
    actor_id: "u1",
    action: "user.update",
    target_type: "user",
    target_id: "u2",
    details: { tier: "power" },
    created_at: "2026-07-01T10:00:00Z",
  },
];

function tree() {
  return (
    <Routes>
      <Route path="/admin/audit" element={<AuditLogPage />} />
    </Routes>
  );
}

test("lists audit entries", async () => {
  server.use(http.get("/admin/audit-logs", () => HttpResponse.json(logs)));
  renderWithProviders(tree(), { route: "/admin/audit" });
  expect(await screen.findByText("user.update")).toBeInTheDocument();
  expect(screen.getByText(/"tier": ?"power"/)).toBeInTheDocument();
});

test("shows an empty state when there are no entries", async () => {
  server.use(http.get("/admin/audit-logs", () => HttpResponse.json([])));
  renderWithProviders(tree(), { route: "/admin/audit" });
  expect(await screen.findByText(/no audit/i)).toBeInTheDocument();
});

test("shows an error state when the request fails", async () => {
  server.use(
    http.get("/admin/audit-logs", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
  );
  renderWithProviders(tree(), { route: "/admin/audit" });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
