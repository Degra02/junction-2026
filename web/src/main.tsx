import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import { AppShell } from "./components/AppShell";
import { AnalysisPage } from "./pages/AnalysisPage";
import { ExtensionPage } from "./pages/ExtensionPage";
import { HomePage } from "./pages/HomePage";
import { MetricsPage } from "./pages/MetricsPage";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Missing #root element in index.html");
}

createRoot(rootElement).render(
  <StrictMode>
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/analyses/:id" element={<AnalysisPage />} />
          <Route path="/extension" element={<ExtensionPage />} />
          <Route path="/metrics" element={<MetricsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  </StrictMode>,
);
