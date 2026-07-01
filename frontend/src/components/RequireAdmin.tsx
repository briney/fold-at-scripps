import type { JSX } from "react";

import { Loader2 } from "lucide-react";
import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "@/hooks/use-auth";

/** Route guard: renders child routes only for authenticated admin users. */
export default function RequireAdmin(): JSX.Element {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div role="status" aria-live="polite" className="flex min-h-svh items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  if (!user || user.role !== "admin") {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
