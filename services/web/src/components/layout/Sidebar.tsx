import { NavLink } from "react-router-dom";
import { LayoutDashboard, Video, Film, Bell, HardDrive, Settings } from "lucide-react";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/cameras", icon: Video, label: "Cameras" },
  { to: "/recordings", icon: Film, label: "Recordings" },
  { to: "/events", icon: Bell, label: "Events" },
  { to: "/storage", icon: HardDrive, label: "Storage" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function Sidebar() {
  return (
    <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
      <div className="p-4 text-lg font-bold text-blue-400 border-b border-gray-800">
        NVR System
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded text-sm ${
                isActive ? "bg-blue-600 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
