import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { RequireAuth } from "./lib/auth";
import { ForgotPage, LoginPage, SetPasswordPage } from "./pages/AuthPages";
import ClientPage from "./pages/ClientPage";
import ClientsPage from "./pages/ClientsPage";
import DealsPage from "./pages/DealsPage";
import GeohubPage from "./pages/GeohubPage";
import InvoiceEditPage from "./pages/InvoiceEditPage";
import InvoicePage from "./pages/InvoicePage";
import InvoicesPage from "./pages/InvoicesPage";
import HomePage from "./pages/HomePage";
import LogPage from "./pages/LogPage";
import SecurityPage from "./pages/SecurityPage";
import StaffPage from "./pages/StaffPage";
import TasksPage from "./pages/TasksPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/set-password" element={<SetPasswordPage />} />
      <Route path="/forgot-password" element={<ForgotPage />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route path="/" element={<HomePage />} />
        <Route path="/clients" element={<ClientsPage />} />
        <Route path="/clients/:id" element={<ClientPage />} />
        <Route path="/deals" element={<DealsPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/invoices" element={<InvoicesPage />} />
        <Route path="/invoices/new" element={<RequireAuth perm="invoices.edit"><InvoiceEditPage /></RequireAuth>} />
        <Route path="/invoices/:id" element={<InvoicePage />} />
        <Route path="/invoices/:id/edit" element={<RequireAuth perm="invoices.edit"><InvoiceEditPage /></RequireAuth>} />
        <Route path="/geohub" element={<GeohubPage />} />
        <Route path="/staff" element={<StaffPage />} />
        <Route path="/log" element={<RequireAuth perm="audit.view"><LogPage /></RequireAuth>} />
        <Route path="/security" element={<SecurityPage />} />
        <Route path="*" element={<div className="page"><h1>Page not found</h1></div>} />
      </Route>
    </Routes>
  );
}
