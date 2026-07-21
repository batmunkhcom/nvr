import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import Dashboard from "../../pages/Dashboard";
import Cameras from "../../pages/Cameras";
import Recordings from "../../pages/Recordings";
import Events from "../../pages/Events";
import Storage from "../../pages/Storage";
import Settings from "../../pages/Settings";
import WizardPage from "../../pages/wizard/Wizard";
import LiveView from "../../pages/LiveViewPage";

export default function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-auto p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/cameras" element={<Cameras />} />
            <Route path="/wizard" element={<WizardPage />} />
            <Route path="/live/:cameraId" element={<LiveView />} />
            <Route path="/recordings" element={<Recordings />} />
            <Route path="/events" element={<Events />} />
            <Route path="/storage" element={<Storage />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/settings/users" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
