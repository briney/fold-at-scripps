import type { ReactElement } from "react";

import { QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { createQueryClient } from "@/lib/query";

export interface RenderOptions {
  route?: string;
}

export function renderWithProviders(ui: ReactElement, opts: RenderOptions = {}): RenderResult {
  const client = createQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[opts.route ?? "/"]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}
