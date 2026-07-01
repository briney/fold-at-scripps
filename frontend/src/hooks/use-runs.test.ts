import type { ReactNode } from "react";
import { createElement } from "react";

import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";

import { useCancelRun, useDeleteRun } from "@/hooks/use-runs";
import { createQueryClient } from "@/lib/query";
import { server } from "@/lib/test/server";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));
import { toast } from "sonner";

function wrapper({ children }: { children: ReactNode }) {
  return createElement(QueryClientProvider, { client: createQueryClient() }, children);
}

test("cancel error surfaces a toast", async () => {
  server.use(
    http.post("/runs/r1/cancel", () =>
      HttpResponse.json({ detail: "Only queued runs can be canceled" }, { status: 409 }),
    ),
  );
  const { result } = renderHook(() => useCancelRun(), { wrapper });
  result.current.mutate("r1");
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/queued/i)));
});

test("delete error surfaces a toast", async () => {
  server.use(
    http.delete("/runs/r1", () =>
      HttpResponse.json({ detail: "Run could not be deleted" }, { status: 500 }),
    ),
  );
  const { result } = renderHook(() => useDeleteRun(), { wrapper });
  result.current.mutate("r1");
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/deleted/i)));
});
