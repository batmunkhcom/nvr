import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "../api/client";
import { NvrEvent } from "../types/event";

export function useEvents(filters?: Record<string, string>) {
  return useQuery({
    queryKey: ["events", filters],
    queryFn: async () => {
      const res = await apiClient.get("/events", { params: { per_page: 50, ...filters } });
      return (res.data?.data || []) as NvrEvent[];
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
