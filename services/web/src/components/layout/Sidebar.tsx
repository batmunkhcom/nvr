import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Video, Film, Bell, HardDrive,
  MapPin, Clock, Users, Settings,
  ChevronsLeft, ChevronsRight,
} from "lucide-react";
import { useUiPreference } from "../../hooks/useUiPreference";
import { useLocale } from "../../i18n/LocaleContext";
import { useAuthStore } from "../../store/authStore";

export default function Sidebar() {
  const [collapsed, setCollapsed] = useUiPreference<boolean>("sidebar_collapsed", false);
  const { t } = useLocale();
  const user = useAuthStore((s) => s.user);

  const navItems = [
    { to: "/dashboard", icon: LayoutDashboard, key: "nav.dashboard" },
    { to: "/cameras", icon: Video, key: "nav.cameras" },
    { to: "/recordings", icon: Film, key: "nav.recordings" },
    { to: "/events", icon: Bell, key: "nav.events" },
    { to: "/storage", icon: HardDrive, key: "nav.storage" },
    { to: "/locations", icon: MapPin, label: "Locations", admin: true },
    { to: "/schedules", icon: Clock, label: "Schedules", admin: true },
    { to: "/settings/users", icon: Users, label: "Users", admin: true },
    { to: "/settings", icon: Settings, key: "nav.settings" },
  ];

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
        {navItems.map(({ to, icon: Icon, key, label, admin }) => {
          if (admin && user?.role !== "admin") return null;
          const display = label || t(key || "");
          return (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? display : undefined}
            className={({ isActive }) =>
              `flex items-center rounded text-sm ${
                collapsed ? "justify-center px-0 py-2.5" : "gap-3 px-3 py-2"
              } ${
                isActive ? "bg-blue-600 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"
              }`
            }
          >
            <Icon size={18} className="flex-shrink-0" />
            {!collapsed && display}
          </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
