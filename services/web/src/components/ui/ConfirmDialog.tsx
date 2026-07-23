import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { useLocale } from "../../i18n/LocaleContext";

interface ConfirmState {
  id: number;
  message: string;
  resolve: (v: boolean) => void;
}

interface ConfirmCtx {
  confirm: (message: string) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmCtx>({} as ConfirmCtx);

let nextId = 0;

export function useConfirm() {
  return useContext(ConfirmContext);
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const { t } = useLocale();
  const [stack, setStack] = useState<ConfirmState[]>([]);

  const confirm = useCallback(
    (message: string): Promise<boolean> =>
      new Promise((resolve) => {
        const id = ++nextId;
        setStack((prev) => [...prev, { id, message, resolve }]);
      }),
    [],
  );

  const dismiss = (id: number, result: boolean) => {
    const item = stack.find((s) => s.id === id);
    if (item) item.resolve(result);
    setStack((prev) => prev.filter((s) => s.id !== id));
  };

  const top = stack.length ? stack[stack.length - 1] : null;

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {top && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => dismiss(top.id, false)}
          />
          <div className="relative bg-gray-900 border border-gray-700 rounded-lg shadow-2xl p-6 max-w-sm w-full mx-4">
            <div className="flex gap-3">
              <AlertTriangle size={20} className="text-yellow-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-white mb-4">{top.message}</p>
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => dismiss(top.id, false)}
                    className="px-4 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-sm text-gray-200"
                  >
                    {t("common.cancel", "Cancel")}
                  </button>
                  <button
                    onClick={() => dismiss(top.id, true)}
                    className="px-4 py-1.5 rounded bg-red-600 hover:bg-red-500 text-sm text-white"
                  >
                    {t("common.confirm", "Confirm")}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
