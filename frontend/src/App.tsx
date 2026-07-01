import type { JSX } from "react";

import { Navigate, Route, Routes } from "react-router-dom";

import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import CatalogPage from "@/pages/CatalogPage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import SubmitPage from "@/pages/SubmitPage";

// Placeholder pages; replaced by real pages in later tasks.
const RunsPage = (): JSX.Element => <h1>Runs</h1>;
const RunDetailPage = (): JSX.Element => <h1>Run</h1>;

export default function App(): JSX.Element {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/tools" replace />} />
          <Route path="/tools" element={<CatalogPage />} />
          <Route path="/tools/:toolId" element={<SubmitPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
