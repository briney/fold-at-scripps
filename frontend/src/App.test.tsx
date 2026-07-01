import { render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import App from "@/App";
import { createQueryClient } from "@/lib/query";

test("lazy-loads and renders the login route through Suspense", async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/login"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  // Login is a public lazy route; it resolves through <Suspense>.
  expect(await screen.findByRole("heading", { name: /log in/i })).toBeInTheDocument();
});
