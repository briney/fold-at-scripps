import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ApiError, getMe, submitRun } from "@/lib/api";
import { server } from "@/lib/test/server";
import type { UserRead } from "@/types/api";

const user: UserRead = {
  id: "u1",
  email: "a@scripps.edu",
  display_name: "A",
  role: "user",
  tier: "standard",
  status: "active",
};

describe("api client", () => {
  it("returns typed JSON on success", async () => {
    server.use(http.get("/auth/me", () => HttpResponse.json(user)));
    await expect(getMe()).resolves.toEqual(user);
  });

  it("throws ApiError with detail on non-2xx", async () => {
    server.use(
      http.get("/auth/me", () =>
        HttpResponse.json({ detail: "Not authenticated" }, { status: 401 }),
      ),
    );
    await expect(getMe()).rejects.toMatchObject({ status: 401, detail: "Not authenticated" });
    await expect(getMe()).rejects.toBeInstanceOf(ApiError);
  });

  it("submitRun posts multipart with tool_id, params JSON, and files", async () => {
    let seen: { toolId: string | null; params: string | null; fileNames: string[] } | null = null;
    server.use(
      http.post("/runs", async ({ request }) => {
        const form = await request.formData();
        seen = {
          toolId: form.get("tool_id") as string | null,
          params: form.get("params") as string | null,
          fileNames: form.getAll("files").map((f) => (f as File).name),
        };
        return HttpResponse.json({ id: "r1" }, { status: 201 });
      }),
    );
    const file = new File(["ATOM"], "backbone.pdb", { type: "chemical/x-pdb" });
    await submitRun("t1", { structure_path: "backbone.pdb", num_sequences: 2 }, [file]);
    expect(seen).toEqual({
      toolId: "t1",
      params: JSON.stringify({ structure_path: "backbone.pdb", num_sequences: 2 }),
      fileNames: ["backbone.pdb"],
    });
  });
});
