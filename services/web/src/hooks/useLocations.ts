import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "../api/client";
import type { Location } from "../types/camera";

export function useLocations() {
  return useQuery({
    queryKey: ["locations"],
    queryFn: async () => {
      const res = await apiClient.get("/locations");
      return (res.data?.data || []) as Location[];
    },
    staleTime: 30_000,
  });
}

export function useLocationMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["locations"] });
    qc.invalidateQueries({ queryKey: ["cameras"] });
  };

  const createLocation = useMutation({
    mutationFn: (payload: { name: string; description?: string }) =>
      apiClient.post("/locations", payload),
    onSuccess: invalidate,
  });

  const updateLocation = useMutation({
    mutationFn: ({
      id,
      ...payload
    }: { id: string; name?: string; description?: string }) =>
      apiClient.patch(`/locations/${id}`, payload),
    onSuccess: invalidate,
  });

  const deleteLocation = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/locations/${id}`),
    onSuccess: invalidate,
  });

  return { createLocation, updateLocation, deleteLocation };
}
