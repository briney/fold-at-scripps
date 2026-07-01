import type { JSX } from "react";

import { FlaskConical, ListChecks, Shield } from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: typeof FlaskConical;
}

const NAV_ITEMS: readonly NavItem[] = [
  { to: "/tools", label: "Tools", icon: FlaskConical },
  { to: "/runs", label: "Runs", icon: ListChecks },
];

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return cn(
    "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/50",
  );
}

/** Left navigation with Tools/Runs links and an admin-only Admin link. */
export default function Sidebar(): JSX.Element {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  return (
    <nav aria-label="Primary" className="flex w-56 flex-col gap-1 border-r bg-background p-3">
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} className={navLinkClass}>
          <Icon className="size-4" aria-hidden="true" />
          {label}
        </NavLink>
      ))}
      {isAdmin ? (
        <NavLink to="/admin" className={navLinkClass}>
          <Shield className="size-4" aria-hidden="true" />
          Admin
        </NavLink>
      ) : null}
    </nav>
  );
}
