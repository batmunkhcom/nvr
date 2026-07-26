import { useRef, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { useLocale } from "../../i18n/LocaleContext";
import { LogOut, Languages, User } from "lucide-react";
import PauseAllButton from "./PauseAllButton";

export default function Topbar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { locale, setLocale, t } = useLocale();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const toggleLocale = () => setLocale(locale === "en" ? "mn" : "en");

  return (
    <header className="h-14 border-b border-gray-800 bg-gray-900 flex items-center justify-between px-6">
      <span className="text-sm text-gray-400">{t("app.title")}</span>
      <div className="flex items-center gap-4">
        <PauseAllButton />
        <button
          onClick={toggleLocale}
          className="text-gray-400 hover:text-white p-1 rounded text-xs font-mono"
          title={`Switch to ${locale === "en" ? "Mongolian" : "English"}`}
        >
          <Languages size={16} className="inline mr-1" />
          {locale.toUpperCase()}
        </button>
        <div ref={ref} className="relative">
          <button
            onClick={() => setOpen(!open)}
            className="flex items-center gap-1.5 text-sm text-gray-300 hover:text-white px-2 py-1 rounded hover:bg-gray-800"
          >
            <User size={16} />
            {user?.username ?? "User"}
          </button>
          {open && (
            <div className="absolute right-0 top-9 w-44 bg-gray-800 border border-gray-700 rounded shadow-xl py-1 z-50">
              <button
                onClick={() => { setOpen(false); navigate("/profile"); }}
                className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-200 hover:bg-gray-700"
              >
                <User size={14} /> Profile
              </button>
              <div className="border-t border-gray-700 my-1" />
              <button
                onClick={() => { setOpen(false); logout(); }}
                className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-400 hover:bg-gray-700"
              >
                <LogOut size={14} /> Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
