import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";

const user = {
  id: "u1",
  email: "a@scripps.edu",
  display_name: "A",
  role: "user",
  tier: "standard",
  status: "active",
};

function loginTree() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<h1>Home</h1>} />
    </Routes>
  );
}

test("login success navigates home", async () => {
  server.use(
    http.post("/auth/login", () => HttpResponse.json(user)),
    http.get("/auth/me", () => HttpResponse.json(user)),
  );
  renderWithProviders(loginTree(), { route: "/login" });
  await userEvent.type(screen.getByLabelText(/email/i), "a@scripps.edu");
  await userEvent.type(screen.getByLabelText(/password/i), "s3cret-pw");
  await userEvent.click(screen.getByRole("button", { name: /log in/i }));
  expect(await screen.findByRole("heading", { name: /home/i })).toBeInTheDocument();
});

test("login shows pending-approval message on 403", async () => {
  server.use(
    http.post("/auth/login", () =>
      HttpResponse.json({ detail: "Account is pending approval" }, { status: 403 }),
    ),
  );
  renderWithProviders(loginTree(), { route: "/login" });
  await userEvent.type(screen.getByLabelText(/email/i), "a@scripps.edu");
  await userEvent.type(screen.getByLabelText(/password/i), "s3cret-pw");
  await userEvent.click(screen.getByRole("button", { name: /log in/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/pending approval/i);
});

test("login shows invalid-credentials message on 401", async () => {
  server.use(
    http.post("/auth/login", () =>
      HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 }),
    ),
  );
  renderWithProviders(loginTree(), { route: "/login" });
  await userEvent.type(screen.getByLabelText(/email/i), "a@scripps.edu");
  await userEvent.type(screen.getByLabelText(/password/i), "wrong-pw-1");
  await userEvent.click(screen.getByRole("button", { name: /log in/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/invalid email or password/i);
});

test("register success shows pending confirmation", async () => {
  server.use(
    http.post("/auth/register", () =>
      HttpResponse.json({ ...user, status: "pending" }, { status: 201 }),
    ),
  );
  renderWithProviders(
    <Routes>
      <Route path="/register" element={<RegisterPage />} />
    </Routes>,
    { route: "/register" },
  );
  await userEvent.type(screen.getByLabelText(/email/i), "new@scripps.edu");
  await userEvent.type(screen.getByLabelText(/display name/i), "New");
  await userEvent.type(screen.getByLabelText(/password/i), "s3cret-pw");
  await userEvent.click(screen.getByRole("button", { name: /register/i }));
  expect(await screen.findByText(/pending approval/i)).toBeInTheDocument();
});

test("register shows 403 not-allowlisted message", async () => {
  server.use(
    http.post("/auth/register", () =>
      HttpResponse.json({ detail: "not approved for registration" }, { status: 403 }),
    ),
  );
  renderWithProviders(
    <Routes>
      <Route path="/register" element={<RegisterPage />} />
    </Routes>,
    { route: "/register" },
  );
  await userEvent.type(screen.getByLabelText(/email/i), "x@scripps.edu");
  await userEvent.type(screen.getByLabelText(/display name/i), "X");
  await userEvent.type(screen.getByLabelText(/password/i), "s3cret-pw");
  await userEvent.click(screen.getByRole("button", { name: /register/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/not approved/i);
});

test("reset password success then invalid", async () => {
  server.use(http.post("/auth/reset-password", () => new HttpResponse(null, { status: 204 })));
  renderWithProviders(
    <Routes>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
    </Routes>,
    { route: "/reset-password?token=abc" },
  );
  await userEvent.type(screen.getByLabelText(/new password/i), "brand-new-pw-9");
  await userEvent.click(screen.getByRole("button", { name: /set password/i }));
  expect(await screen.findByText(/password updated/i)).toBeInTheDocument();

  server.use(
    http.post("/auth/reset-password", () =>
      HttpResponse.json({ detail: "Invalid or expired reset token" }, { status: 400 }),
    ),
  );
  renderWithProviders(
    <Routes>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
    </Routes>,
    { route: "/reset-password?token=bad" },
  );
  await userEvent.type(screen.getByLabelText(/new password/i), "brand-new-pw-9");
  await userEvent.click(screen.getByRole("button", { name: /set password/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/invalid or expired/i);
});
