import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import en from "./translations/en.json";

type Locale = "en" | "mn";
type Translations = Record<string, string | Record<string, unknown>>;

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, fallback?: string) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

let _cachedLocale: Locale = "en";

function resolveDot(
  obj: Record<string, unknown>,
  path: string,
): string | undefined {
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current == null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === "string" ? current : undefined;
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(
    () => (localStorage.getItem("locale") as Locale) || "en",
  );
  const [messages, setMessages] = useState<Translations>(en);

  useEffect(() => {
    if (locale === "en") {
      setMessages(en);
      return;
    }
    import(`./translations/${locale}.json`)
      .then((mod) => setMessages(mod.default || mod))
      .catch(() => setMessages({}));
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    _cachedLocale = next;
    setLocaleState(next);
    try {
      localStorage.setItem("locale", next);
    } catch {
      /* ignore storage errors */
    }
  }, []);

  const t = useCallback(
    (key: string, fallback?: string): string => {
      const resolved = resolveDot(messages, key);
      return resolved ?? fallback ?? key;
    },
    [messages],
  );

  return (
    <LocaleContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return ctx;
}

export function getLocale(): Locale {
  return _cachedLocale;
}
