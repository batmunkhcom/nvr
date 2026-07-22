import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Video, Film, Bell, HardDrive, Settings,
  ChevronsLeft, ChevronsRight,
} from "lucide-react";
import { useUiPreference } from "../../hooks/useUiPreference";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/cameras", icon: Video, label: "Cameras" },
  { to: "/recordings", icon: Film, label: "Recordings" },
  { to: "/events", icon: Bell, label: "Events" },
  { to: "/storage", icon: HardDrive, label: "Storage" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useUiPreference<boolean>("sidebar_collapsed", false);

  return (
    <aside
      className={`bg-gray-900 border-r border-gray-800 flex flex-col transition-all duration-200 ${
        collapsed ? "w-14" : "w-56"
      }`}
    >
      <div
        className={`p-4 border-b border-gray-800 flex items-center ${
          collapsed ? "justify-center" : "justify-between"
        }`}
      >
        {!collapsed && <span className="text-lg font-bold text-blue-400">NVR System</span>}
        <button
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="p-1 rounded text-gray-500 hover:bg-gray-800 hover:text-white"
        >
          {collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}
        </button>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              `flex items-center rounded text-sm ${
                collapsed ? "justify-center px-0 py-2.5" : "gap-3 px-3 py-2"
              } ${
                isActive ? "bg-blue-600 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"
              }`
            }
          >
            <Icon size={18} className="flex-shrink-0" />
            {!collapsed && label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
