import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import SettingsPage from "@/pages/admin/SettingsPage";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));
import { toast } from "sonner";

const settings = {
  maintenance_mode: false,
  standard_max_concurrent_runs: 3,
  power_max_concurrent_runs: 12,
  updated_at: "2026-07-01T00:00:00Z",
};

function tree() {
  return (
    <Routes>
      <Route path="/admin/settings" element={<SettingsPage />} />
    </Routes>
  );
}

test("loads current settings and saves changes", async () => {
  let sent: unknown = null;
  server.use(
    http.get("/admin/settings", () => HttpResponse.json(settings)),
    http.patch("/admin/settings", async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json({ ...settings, standard_max_concurrent_runs: 5 });
    }),
  );
  renderWithProviders(tree(), { route: "/admin/settings" });
  const std = await screen.findByLabelText(/standard/i);
  await userEvent.clear(std);
  await userEvent.type(std, "5");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalled());
  expect(sent).toMatchObject({ standard_max_concurrent_runs: 5 });
});

test("sends only changed fields, preserving untouched ones", async () => {
  let sent: Record<string, unknown> | null = null;
  server.use(
    http.get("/admin/settings", () => HttpResponse.json(settings)),
    http.patch("/admin/settings", async ({ request }) => {
      sent = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...settings, standard_max_concurrent_runs: 7 });
    }),
  );
  renderWithProviders(tree(), { route: "/admin/settings" });
  const std = await screen.findByLabelText(/standard/i);
  await userEvent.clear(std);
  await userEvent.type(std, "7");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await vi.waitFor(() => expect(sent).not.toBeNull());
  const payload = sent as unknown as Record<string, unknown>;
  expect(payload.standard_max_concurrent_runs).toBe(7);
  expect(payload).not.toHaveProperty("power_max_concurrent_runs");
  expect(payload).not.toHaveProperty("maintenance_mode");
});
