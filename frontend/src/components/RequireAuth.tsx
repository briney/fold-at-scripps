import type { JSX } from "react";

import { Loader2 } from "lucide-react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/hooks/use-auth";

/** Route guard: renders child routes when the user is authenticated. */
export default function RequireAuth(): JSX.Element {
  const { isLoading, isError } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div role="status" aria-live="polite" className="flex min-h-svh items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  if (isError) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
