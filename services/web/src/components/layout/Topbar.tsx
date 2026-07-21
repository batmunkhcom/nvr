import { useAuthStore } from "../../store/authStore";
import { LogOut } from "lucide-react";

export default function Topbar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  return (
    <header className="h-14 border-b border-gray-800 bg-gray-900 flex items-center justify-between px-6">
      <span className="text-sm text-gray-400">Network Video Recorder</span>
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-300">{user?.username ?? "User"}</span>
        <button
          onClick={logout}
          className="text-gray-400 hover:text-white p-1 rounded"
          title="Logout"
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}
