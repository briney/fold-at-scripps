import type { JSX } from "react";

import { Outlet } from "react-router-dom";

import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";

/** Authenticated app layout: sidebar, top bar, and the routed page. */
export default function AppShell(): JSX.Element {
  return (
    <div className="flex min-h-svh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
