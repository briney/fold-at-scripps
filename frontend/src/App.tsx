import type { JSX } from "react";

import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import AppShell from "@/components/AppShell";
import RequireAdmin from "@/components/RequireAdmin";
import RequireAuth from "@/components/RequireAuth";
import Loading from "@/components/states/Loading";
import { Toaster } from "@/components/ui/sonner";
import AdminLayout from "@/pages/admin/AdminLayout";

const LoginPage = lazy(() => import("@/pages/LoginPage"));
const RegisterPage = lazy(() => import("@/pages/RegisterPage"));
const ResetPasswordPage = lazy(() => import("@/pages/ResetPasswordPage"));
const CatalogPage = lazy(() => import("@/pages/CatalogPage"));
const SubmitPage = lazy(() => import("@/pages/SubmitPage"));
const RunsPage = lazy(() => import("@/pages/RunsPage"));
const RunDetailPage = lazy(() => import("@/pages/RunDetailPage"));
const UsersPage = lazy(() => import("@/pages/admin/UsersPage"));
const AllowlistPage = lazy(() => import("@/pages/admin/AllowlistPage"));
const SettingsPage = lazy(() => import("@/pages/admin/SettingsPage"));
const AdminCatalogPage = lazy(() => import("@/pages/admin/CatalogPage"));
const AdminRunsPage = lazy(() => import("@/pages/admin/AdminRunsPage"));
const AdminRunDetailPage = lazy(() => import("@/pages/admin/AdminRunDetailPage"));
const AuditLogPage = lazy(() => import("@/pages/admin/AuditLogPage"));

export default function App(): JSX.Element {
  return (
    <>
      <Suspense fallback={<Loading />}>
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
      </Suspense>
      <Toaster />
    </>
  );
}
