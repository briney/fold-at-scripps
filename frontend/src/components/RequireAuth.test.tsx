import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";

import RequireAuth from "@/components/RequireAuth";
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

function tree() {
  return (
    <Routes>
      <Route path="/login" element={<h1>Login</h1>} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<h1>Protected</h1>} />
      </Route>
    </Routes>
  );
}

test("renders protected content when authenticated", async () => {
  server.use(http.get("/auth/me", () => HttpResponse.json(user)));
  renderWithProviders(tree(), { route: "/" });
  expect(await screen.findByRole("heading", { name: /protected/i })).toBeInTheDocument();
});

test("redirects to /login when unauthenticated", async () => {
  server.use(
    http.get("/auth/me", () => HttpResponse.json({ detail: "Not authenticated" }, { status: 401 })),
  );
  renderWithProviders(tree(), { route: "/" });
  await waitFor(() => expect(screen.getByRole("heading", { name: /login/i })).toBeInTheDocument());
});
