import { useAuthStore } from "../../store/authStore";
import { useLocale } from "../../i18n/LocaleContext";
import { LogOut, Languages } from "lucide-react";

export default function Topbar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { locale, setLocale, t } = useLocale();

  const toggleLocale = () => setLocale(locale === "en" ? "mn" : "en");

  return (
    <header className="h-14 border-b border-gray-800 bg-gray-900 flex items-center justify-between px-6">
      <span className="text-sm text-gray-400">{t("app.title")}</span>
      <div className="flex items-center gap-4">
        <button
          onClick={toggleLocale}
          className="text-gray-400 hover:text-white p-1 rounded text-xs font-mono"
          title={`Switch to ${locale === "en" ? "Mongolian" : "English"}`}
        >
          <Languages size={16} className="inline mr-1" />
          {locale.toUpperCase()}
        </button>
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
