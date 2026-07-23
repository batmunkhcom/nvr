import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Video, Film, Bell, HardDrive,
  MapPin, Clock, Users, Settings,
  ChevronsLeft, ChevronsRight,
  BookOpen, ExternalLink, Code, MessageSquare,
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
        {!collapsed && <span className="text-lg font-bold text-blue-400">mBm NVR</span>}
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

      {!collapsed && (
        <div className="p-2 border-t border-gray-800 text-[10px] text-gray-500 space-y-0.5">
          <a
            href="https://github.com/batmunkhcom/nvr/releases"
            target="_blank"
            rel="noopener"
            className="flex items-center gap-1.5 px-2 py-1 hover:text-gray-200 rounded transition-colors"
          >
            <BookOpen size={11} /> Changelog
          </a>
          <a
            href="https://github.com/batmunkhcom/nvr#readme"
            target="_blank"
            rel="noopener"
            className="flex items-center gap-1.5 px-2 py-1 hover:text-gray-200 rounded transition-colors"
          >
            <ExternalLink size={11} /> Docs
          </a>
          <a
            href="/docs"
            target="_blank"
            rel="noopener"
            className="flex items-center gap-1.5 px-2 py-1 hover:text-gray-200 rounded transition-colors"
          >
            <Code size={11} /> API Docs
          </a>
          <a
            href="https://github.com/batmunkhcom/nvr/issues"
            target="_blank"
            rel="noopener"
            className="flex items-center gap-1.5 px-2 py-1 hover:text-gray-200 rounded transition-colors"
          >
            <MessageSquare size={11} /> Feedback
          </a>
          <div className="px-2 pt-1 text-gray-500 leading-tight">
            mBm NVR System v0.2<br />
            <span className="text-gray-600">mBm TECHNOLOGY since &copy; 2023</span>
          </div>
        </div>
      )}
    </aside>
  );
}
