import type { JSX } from "react";

import { Navigate, Route, Routes } from "react-router-dom";

import AppShell from "@/components/AppShell";
import RequireAdmin from "@/components/RequireAdmin";
import RequireAuth from "@/components/RequireAuth";
import { Toaster } from "@/components/ui/sonner";
import CatalogPage from "@/pages/CatalogPage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import RunDetailPage from "@/pages/RunDetailPage";
import RunsPage from "@/pages/RunsPage";
import SubmitPage from "@/pages/SubmitPage";
import AdminLayout from "@/pages/admin/AdminLayout";

// Placeholder admin screens — replaced by Tasks 3–8.
const UsersPage = (): JSX.Element => <h1>Users</h1>;
const AllowlistPage = (): JSX.Element => <h1>Allowlist</h1>;
const SettingsPage = (): JSX.Element => <h1>Settings</h1>;
const AdminCatalogPage = (): JSX.Element => <h1>Catalog</h1>;
const AdminRunsPage = (): JSX.Element => <h1>Runs</h1>;
const AdminRunDetailPage = (): JSX.Element => <h1>Run Detail</h1>;
const AuditLogPage = (): JSX.Element => <h1>Audit Log</h1>;

export default function App(): JSX.Element {
  return (
    <>
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
            <Route path="admin" element={<RequireAdmin />}>
              <Route element={<AdminLayout />}>
                <Route index element={<Navigate to="/admin/users" replace />} />
                <Route path="users" element={<UsersPage />} />
                <Route path="allowed-emails" element={<AllowlistPage />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="catalog" element={<AdminCatalogPage />} />
                <Route path="runs" element={<AdminRunsPage />} />
                <Route path="runs/:runId" element={<AdminRunDetailPage />} />
                <Route path="audit" element={<AuditLogPage />} />
              </Route>
            </Route>
          </Route>
        </Route>
      </Routes>
      <Toaster />
    </>
  );
}
