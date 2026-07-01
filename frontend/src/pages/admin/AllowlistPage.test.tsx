import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import AllowlistPage from "@/pages/admin/AllowlistPage";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));
import { toast } from "sonner";

const rows = [{ id: "e1", email: "approved@scripps.edu", created_at: "2026-07-01T00:00:00Z" }];

function tree() {
  return (
    <Routes>
      <Route path="/admin/allowed-emails" element={<AllowlistPage />} />
    </Routes>
  );
}

test("lists allowlisted emails", async () => {
  server.use(http.get("/admin/allowed-emails", () => HttpResponse.json(rows)));
  renderWithProviders(tree(), { route: "/admin/allowed-emails" });
  expect(await screen.findByText("approved@scripps.edu")).toBeInTheDocument();
});

test("shows an error toast when adding a duplicate", async () => {
  server.use(
    http.get("/admin/allowed-emails", () => HttpResponse.json(rows)),
    http.post("/admin/allowed-emails", () =>
      HttpResponse.json({ detail: "already on the allowlist" }, { status: 409 }),
    ),
  );
  renderWithProviders(tree(), { route: "/admin/allowed-emails" });
  await userEvent.type(await screen.findByLabelText(/add email/i), "approved@scripps.edu");
  await userEvent.click(screen.getByRole("button", { name: /^add$/i }));
  await vi.waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/allowlist/i)),
  );
});

test("removes an email after confirming", async () => {
  server.use(
    http.get("/admin/allowed-emails", () => HttpResponse.json(rows)),
    http.delete("/admin/allowed-emails/e1", () => new HttpResponse(null, { status: 204 })),
  );
  renderWithProviders(tree(), { route: "/admin/allowed-emails" });
  await userEvent.click(await screen.findByRole("button", { name: /remove/i }));
  const dialog = await screen.findByRole("alertdialog");
  await userEvent.click(within(dialog).getByRole("button", { name: /remove|confirm/i }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalled());
});
