import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import {
  ApiError,
  adminAddAllowedEmail,
  adminListRuns,
  adminListUsers,
  adminUpdateUser,
} from "@/lib/api";
import { server } from "@/lib/test/server";
import type { AdminUserRead } from "@/types/api";

const adminUser: AdminUserRead = {
  id: "u1",
  email: "a@scripps.edu",
  display_name: "A",
  role: "admin",
  tier: "power",
  status: "active",
  max_concurrent_runs_override: null,
  created_at: "2026-07-01T00:00:00Z",
};

describe("admin api client", () => {
  it("lists users (typed)", async () => {
    server.use(http.get("/admin/users", () => HttpResponse.json([adminUser])));
    await expect(adminListUsers()).resolves.toEqual([adminUser]);
  });

  it("throws ApiError with detail on 409 (duplicate allowlist email)", async () => {
    server.use(
      http.post("/admin/allowed-emails", () =>
        HttpResponse.json({ detail: "already on the allowlist" }, { status: 409 }),
      ),
    );
    await expect(adminAddAllowedEmail("dup@scripps.edu")).rejects.toBeInstanceOf(ApiError);
    await expect(adminAddAllowedEmail("dup@scripps.edu")).rejects.toMatchObject({ status: 409 });
  });

  it("PATCHes a user with a partial body", async () => {
    let seen: unknown = null;
    server.use(
      http.patch("/admin/users/u1", async ({ request }) => {
        seen = await request.json();
        return HttpResponse.json({ ...adminUser, tier: "standard" });
      }),
    );
    await adminUpdateUser("u1", { tier: "standard" });
    expect(seen).toEqual({ tier: "standard" });
  });

  it("builds the runs query string from filters", async () => {
    let url = "";
    server.use(
      http.get("/admin/runs", ({ request }) => {
        url = new URL(request.url).search;
        return HttpResponse.json([]);
      }),
    );
    await adminListRuns({ status: "queued", userId: "u1" });
    expect(url).toContain("status=queued");
    expect(url).toContain("user_id=u1");
  });
});
