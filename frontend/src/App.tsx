import type { ReactElement } from "react";
import { Route, Routes } from "react-router-dom";
import {
  ApprovalsQueue,
  Dashboard,
  DocumentDetail,
  DocumentNew,
  Login,
  NotFound,
  Register,
  RevisionNew,
  Verify,
  VerificationDetail,
  VerificationHistory,
} from "./pages/placeholders";

export function AppRoutes(): ReactElement {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/" element={<Dashboard />} />
      <Route path="/documents/new" element={<DocumentNew />} />
      <Route path="/documents/:id" element={<DocumentDetail />} />
      <Route path="/documents/:id/revisions/new" element={<RevisionNew />} />
      <Route path="/approvals" element={<ApprovalsQueue />} />
      <Route path="/verify" element={<Verify />} />
      <Route path="/verifications" element={<VerificationHistory />} />
      <Route path="/verifications/:id" element={<VerificationDetail />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
