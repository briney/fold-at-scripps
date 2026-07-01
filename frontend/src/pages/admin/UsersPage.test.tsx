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
  {
    id: "u1",
    email: "alice@scripps.edu",
    display_name: "Alice",
    role: "user",
    tier: "standard",
    status: "active",
    max_concurrent_runs_override: null,
    created_at: "2026-07-01T00:00:00Z",
  },
  {
    id: "u2",
    email: "bob@scripps.edu",
    display_name: "Bob",
    role: "user",
    tier: "standard",
    status: "pending",
    max_concurrent_runs_override: null,
    created_at: "2026-07-01T00:00:00Z",
  },
];

function tree() {
  return (
    <Routes>
      <Route path="/admin/users" element={<UsersPage />} />
    </Routes>
  );
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
      HttpResponse.json(
        { token: "SECRET-TOKEN-123", expires_at: "2026-07-02T00:00:00Z" },
        { status: 201 },
      ),
    ),
  );
  renderWithProviders(tree(), { route: "/admin/users" });
  const row = (await screen.findByText("alice@scripps.edu")).closest("tr")!;
  await userEvent.click(within(row).getByRole("button", { name: /reset password/i }));
  expect(await screen.findByDisplayValue("SECRET-TOKEN-123")).toBeInTheDocument();
});
