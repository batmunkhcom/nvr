import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "../api/client";
import { NvrEvent } from "../types/event";

export interface EventsPage {
  data: NvrEvent[];
  metadata: { page: number; per_page: number; total: number };
}

export function useEvents(filters?: Record<string, string>) {
  return useQuery({
    queryKey: ["events", filters],
    queryFn: async () => {
      const res = await apiClient.get("/events", { params: { per_page: 10, ...filters } });
      return {
        data: (res.data?.data || []) as NvrEvent[],
        metadata: res.data?.metadata || { page: 1, per_page: 10, total: 0 },
      } as EventsPage;
    },
    refetchInterval: 15_000,
  });
}

export function useAcknowledgeEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (eventId: string) => {
      await apiClient.patch(`/events/${eventId}/acknowledge`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["events"] }),
  });
}
