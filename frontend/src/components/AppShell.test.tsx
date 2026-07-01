import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";

import AppShell from "@/components/AppShell";
import { renderWithProviders } from "@/lib/test/render";
import { server } from "@/lib/test/server";

const user = {
  id: "u1",
  email: "a@scripps.edu",
  display_name: "A",
  role: "user",
  tier: "standard",
  status: "active",
};

test("shows Tools and Runs nav, hides Admin for non-admins", async () => {
  server.use(http.get("/auth/me", () => HttpResponse.json(user)));
  renderWithProviders(
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<div />} />
      </Route>
    </Routes>,
    { route: "/" },
  );
  expect(await screen.findByRole("link", { name: /tools/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /runs/i })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /admin/i })).not.toBeInTheDocument();
});
