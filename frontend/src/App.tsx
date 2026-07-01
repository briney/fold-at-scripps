import type { JSX } from "react";

import { Navigate, Route, Routes } from "react-router-dom";

import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";

// Placeholder pages; replaced by real pages in later tasks.
const LoginPage = (): JSX.Element => <h1>Log in</h1>;
const RegisterPage = (): JSX.Element => <h1>Register</h1>;
const ResetPasswordPage = (): JSX.Element => <h1>Reset password</h1>;
const ToolsPage = (): JSX.Element => <h1>Tools</h1>;
const ToolDetailPage = (): JSX.Element => <h1>Tool</h1>;
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
          <Route path="/tools" element={<ToolsPage />} />
          <Route path="/tools/:toolId" element={<ToolDetailPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
