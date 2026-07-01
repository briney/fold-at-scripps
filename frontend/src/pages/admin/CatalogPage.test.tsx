import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import CatalogPage from "@/pages/admin/CatalogPage";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));
import { toast } from "sonner";

const tools = [
  {
    id: "t1",
    name: "antifold",
    version: "1.0.0",
    category: "inverse-folding",
    enabled: true,
    gpu_count: 1,
    description: "d",
    image_tag: "a:1",
    default_timeout: 600,
    supports_batch: false,
  },
  {
    id: "t2",
    name: "ablang2",
    version: "1.0.0",
    category: "embedding",
    enabled: false,
    gpu_count: 1,
    description: "d",
    image_tag: "b:1",
    default_timeout: 600,
    supports_batch: true,
  },
];

function tree() {
  return (
    <Routes>
      <Route path="/admin/catalog" element={<CatalogPage />} />
    </Routes>
  );
}

test("lists all tools including disabled", async () => {
  server.use(http.get("/admin/tools", () => HttpResponse.json(tools)));
  renderWithProviders(tree(), { route: "/admin/catalog" });
  expect(await screen.findByText("antifold")).toBeInTheDocument();
  expect(screen.getByText("ablang2")).toBeInTheDocument();
});

test("toggles a tool and toasts on success", async () => {
  const patched = vi.fn();
  server.use(
    http.get("/admin/tools", () => HttpResponse.json(tools)),
    http.patch("/admin/tools/t2", async ({ request }) => {
      patched((await request.json()) as { enabled: boolean });
      return HttpResponse.json({ ...tools[1], enabled: true });
    }),
  );
  renderWithProviders(tree(), { route: "/admin/catalog" });
  const row = (await screen.findByText("ablang2")).closest("tr");
  expect(row).not.toBeNull();
  await userEvent.click(within(row as HTMLElement).getByRole("switch"));
  await vi.waitFor(() => expect(patched).toHaveBeenCalledWith({ enabled: true }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalled());
});

test("syncs the catalog and toasts the counts", async () => {
  server.use(
    http.get("/admin/tools", () => HttpResponse.json(tools)),
    http.post("/admin/catalog/sync", () => HttpResponse.json({ added: 2, updated: 1 })),
  );
  renderWithProviders(tree(), { route: "/admin/catalog" });
  await screen.findByText("antifold");
  await userEvent.click(screen.getByRole("button", { name: /sync/i }));
  await vi.waitFor(() =>
    expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/2 added/i)),
  );
});
