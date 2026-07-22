import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "../api/client";

type UiConfig = Record<string, unknown>;

export function useUiConfig() {
  return useQuery({
    queryKey: ["ui-config"],
    queryFn: async () => {
      const res = await apiClient.get("/system/ui-config");
      return (res.data?.data || {}) as UiConfig;
    },
    staleTime: 60_000,
  });
}

/**
 * Read/write a single ui.* preference persisted in system_config (DB).
 * Falls back to `defaultValue` until loaded or when unset.
 */
export function useUiPreference<T>(key: string, defaultValue: T) {
  const qc = useQueryClient();
  const { data } = useUiConfig();

  const raw = data?.[`ui.${key}`];
  const value = (raw === undefined || raw === null ? defaultValue : raw) as T;

  const mutation = useMutation({
    mutationFn: (v: T) =>
      apiClient.patch("/system/ui-config", { key: `ui.${key}`, value: v }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui-config"] });
    },
  });

  return [value, mutation.mutate] as const;
}
