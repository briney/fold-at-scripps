import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { server } from "@/lib/test/server";
import { renderWithProviders } from "@/lib/test/render";
import SubmitPage from "@/pages/SubmitPage";
import antifold from "@/lib/schema-form/__fixtures__/antifold.json";

const tool = {
  id: "t1",
  name: "antifold",
  version: "1.0.0",
  category: "inverse-folding",
  gpu_count: 1,
  description: "d",
  supports_batch: false,
  image_tag: "antifold:1",
  default_timeout: 600,
  input_schema: antifold,
};

function tree() {
  return (
    <Routes>
      <Route path="/tools/:toolId" element={<SubmitPage />} />
      <Route path="/runs/:runId" element={<h1>Run Detail</h1>} />
    </Routes>
  );
}

test("submits and navigates to the new run", async () => {
  server.use(
    http.get("/tools/t1", () => HttpResponse.json(tool)),
    http.post("/runs", () =>
      HttpResponse.json(
        {
          id: "r1",
          tool: { id: "t1", name: "antifold", version: "1.0.0", category: "inverse-folding" },
          status: "queued",
          created_at: "",
          started_at: null,
          finished_at: null,
        },
        { status: 201 },
      ),
    ),
  );
  renderWithProviders(tree(), { route: "/tools/t1" });
  await userEvent.upload(await screen.findByLabelText(/structure path/i), new File(["A"], "b.pdb"));
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(await screen.findByRole("heading", { name: /run detail/i })).toBeInTheDocument();
});

test("shows quota message on 429", async () => {
  server.use(
    http.get("/tools/t1", () => HttpResponse.json(tool)),
    http.post("/runs", () =>
      HttpResponse.json({ detail: "Concurrency limit of 3 reached" }, { status: 429 }),
    ),
  );
  renderWithProviders(tree(), { route: "/tools/t1" });
  await userEvent.upload(await screen.findByLabelText(/structure path/i), new File(["A"], "b.pdb"));
  await userEvent.click(screen.getByRole("button", { name: /submit/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/quota|limit/i);
});
