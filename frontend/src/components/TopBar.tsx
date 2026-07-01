import type { JSX } from "react";
import { useState } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Moon, Sun, User } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/hooks/use-auth";
import { logout } from "@/lib/api";

/** Top bar with the app title, theme toggle, and user menu. */
export default function TopBar(): JSX.Element {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [isDark, setIsDark] = useState(
    () => typeof document !== "undefined" && document.documentElement.classList.contains("dark"),
  );

  function handleToggleTheme(): void {
    const next = document.documentElement.classList.toggle("dark");
    setIsDark(next);
  }

  async function handleLogout(): Promise<void> {
    try {
      await logout();
    } finally {
      queryClient.setQueryData(["me"], null);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      navigate("/login", { replace: true });
    }
  }

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4">
      <span className="text-lg font-semibold tracking-tight text-primary">fold@Scripps</span>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={handleToggleTheme}
          aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
        >
          {isDark ? (
            <Sun className="size-4" aria-hidden="true" />
          ) : (
            <Moon className="size-4" aria-hidden="true" />
          )}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="icon" aria-label="User menu">
              <User className="size-4" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{user?.email ?? "Account"}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void handleLogout()}>
              <LogOut className="size-4" aria-hidden="true" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
