import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";

import RequireAdmin from "@/components/RequireAdmin";
import { renderWithProviders } from "@/lib/test/render";
import { server } from "@/lib/test/server";

function tree() {
  return (
    <Routes>
      <Route path="/" element={<h1>Home</h1>} />
      <Route element={<RequireAdmin />}>
        <Route path="/admin" element={<h1>Admin Area</h1>} />
      </Route>
    </Routes>
  );
}

const base = {
  id: "u1",
  email: "a@scripps.edu",
  display_name: "A",
  tier: "standard",
  status: "active",
};

test("renders admin content for an admin", async () => {
  server.use(http.get("/auth/me", () => HttpResponse.json({ ...base, role: "admin" })));
  renderWithProviders(tree(), { route: "/admin" });
  expect(await screen.findByRole("heading", { name: /admin area/i })).toBeInTheDocument();
});

test("redirects a non-admin away from /admin", async () => {
  server.use(http.get("/auth/me", () => HttpResponse.json({ ...base, role: "user" })));
  renderWithProviders(tree(), { route: "/admin" });
  await waitFor(() => expect(screen.getByRole("heading", { name: /home/i })).toBeInTheDocument());
});
