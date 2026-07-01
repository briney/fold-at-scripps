import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "@/lib/test/render";
import AdminLayout from "@/pages/admin/AdminLayout";

test("shows the six admin tab links", () => {
  renderWithProviders(
    <Routes>
      <Route element={<AdminLayout />}>
        <Route path="/admin" element={<div />} />
      </Route>
    </Routes>,
    { route: "/admin" },
  );
  for (const name of [/users/i, /allowlist/i, /settings/i, /catalog/i, /runs/i, /audit/i]) {
    expect(screen.getByRole("link", { name })).toBeInTheDocument();
  }
});
