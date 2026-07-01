import { screen } from "@testing-library/react";

import App from "@/App";
import { renderWithProviders } from "@/lib/test/render";

test("renders the login page on the public route", () => {
  renderWithProviders(<App />, { route: "/login" });
  expect(screen.getByRole("heading", { name: /log in/i })).toBeInTheDocument();
});
