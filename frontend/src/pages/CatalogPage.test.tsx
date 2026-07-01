import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import CatalogPage from "@/pages/CatalogPage";

const tools = [
  {
    id: "t1",
    name: "antifold",
    version: "1.0.0",
    category: "inverse-folding",
    gpu_count: 1,
    description: "inverse folding",
    supports_batch: false,
  },
  {
    id: "t2",
    name: "ablang2",
    version: "1.0.0",
    category: "embedding",
    gpu_count: 1,
    description: "embeddings",
    supports_batch: true,
  },
];

function tree() {
  return (
    <Routes>
      <Route path="/tools" element={<CatalogPage />} />
      <Route path="/tools/:toolId" element={<h1>Submit</h1>} />
    </Routes>
  );
}

test("lists tools grouped by category and filters", async () => {
  server.use(http.get("/tools", () => HttpResponse.json(tools)));
  renderWithProviders(tree(), { route: "/tools" });
  expect(await screen.findByText("antifold")).toBeInTheDocument();
  expect(screen.getByText("ablang2")).toBeInTheDocument();
  expect(screen.getByText(/inverse-folding/i)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText(/search tools/i), "ablang");
  expect(screen.queryByText("antifold")).not.toBeInTheDocument();
  expect(screen.getByText("ablang2")).toBeInTheDocument();
});

test("navigates to submit on card click", async () => {
  server.use(http.get("/tools", () => HttpResponse.json(tools)));
  renderWithProviders(tree(), { route: "/tools" });
  await userEvent.click(await screen.findByRole("link", { name: /antifold/i }));
  expect(await screen.findByRole("heading", { name: /submit/i })).toBeInTheDocument();
});

test("shows empty state when no tools", async () => {
  server.use(http.get("/tools", () => HttpResponse.json([])));
  renderWithProviders(tree(), { route: "/tools" });
  expect(await screen.findByText(/no tools/i)).toBeInTheDocument();
});

test("shows error state on failure", async () => {
  server.use(http.get("/tools", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
  renderWithProviders(tree(), { route: "/tools" });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
