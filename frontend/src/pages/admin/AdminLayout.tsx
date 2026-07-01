import type { JSX } from "react";

import { NavLink, Outlet } from "react-router-dom";

import { cn } from "@/lib/utils";

interface AdminTab {
  to: string;
  label: string;
}

const ADMIN_TABS: readonly AdminTab[] = [
  { to: "/admin/users", label: "Users" },
  { to: "/admin/allowed-emails", label: "Allowlist" },
  { to: "/admin/settings", label: "Settings" },
  { to: "/admin/catalog", label: "Catalog" },
  { to: "/admin/runs", label: "Runs" },
  { to: "/admin/audit", label: "Audit" },
];

function tabClass({ isActive }: { isActive: boolean }): string {
  return cn(
    "border-b-2 px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "border-primary text-foreground"
      : "border-transparent text-muted-foreground hover:text-foreground",
  );
}

/** Admin console shell: a secondary tab-nav across the six admin screens. */
export default function AdminLayout(): JSX.Element {
  return (
    <div className="space-y-6">
      <nav aria-label="Admin sections" className="flex gap-1 border-b">
        {ADMIN_TABS.map(({ to, label }) => (
          <NavLink key={to} to={to} className={tabClass}>
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
