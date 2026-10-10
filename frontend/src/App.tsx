import type { ReactElement } from "react";
import { Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AppShell } from "./components/AppShell";
import { ApprovalsQueue } from "./pages/ApprovalsQueue";
import { Dashboard } from "./pages/Dashboard";
import { DocumentDetail } from "./pages/DocumentDetail";
import { DocumentNew } from "./pages/DocumentNew";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/placeholders";
import { RevisionNew } from "./pages/RevisionNew";
import { Register } from "./pages/Register";
import { VerificationDetail } from "./pages/VerificationDetail";
import { VerificationHistory } from "./pages/VerificationHistory";
import { Verify } from "./pages/Verify";

export function AppRoutes(): ReactElement {
  return (
    <AuthProvider>
      <AppShell>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/documents/new"
            element={
              <ProtectedRoute>
                <DocumentNew />
              </ProtectedRoute>
            }
          />
          <Route
            path="/documents/:id"
            element={
              <ProtectedRoute>
                <DocumentDetail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/documents/:id/revisions/new"
            element={
              <ProtectedRoute>
                <RevisionNew />
              </ProtectedRoute>
            }
          />
          <Route
            path="/approvals"
            element={
              <ProtectedRoute>
                <ApprovalsQueue />
              </ProtectedRoute>
            }
          />
          {/* Public: PUBLIC_VERIFY allows anonymous verification (docs/04_API_SPEC.md). */}
          <Route path="/verify" element={<Verify />} />
          <Route
            path="/verifications"
            element={
              <ProtectedRoute>
                <VerificationHistory />
              </ProtectedRoute>
            }
          />
          <Route
            path="/verifications/:id"
            element={
              <ProtectedRoute>
                <VerificationDetail />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AppShell>
    </AuthProvider>
  );
}
