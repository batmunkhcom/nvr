import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "../api/client";
import type { RecordingSchedule } from "../types/recording";

export function useRecordingSchedules(cameraId?: string) {
  const params: Record<string, string> = {};
  if (cameraId) params.camera_id = cameraId;
  return useQuery({
    queryKey: ["recording-schedules", cameraId],
    queryFn: () =>
      apiClient
        .get("/recording-schedules", { params })
        .then((r) => (r.data?.data || []) as RecordingSchedule[]),
  });
}

export function useRecordingScheduleMutations() {
  const qc = useQueryClient();
  const inval = () => qc.invalidateQueries({ queryKey: ["recording-schedules"] });

  const create = useMutation({
    mutationFn: (body: {
      camera_id: string;
      schedule_name: string;
      days_of_week?: number[];
      time_start?: string;
      time_end?: string;
      schedule_type?: string;
    }) => apiClient.post("/recording-schedules", body),
    onSuccess: inval,
  });
  const update = useMutation({
    mutationFn: ({ id, ...body }: { id: string; is_active?: boolean; days_of_week?: number[]; time_start?: string; time_end?: string }) =>
      apiClient.patch(`/recording-schedules/${id}`, body),
    onSuccess: inval,
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/recording-schedules/${id}`),
    onSuccess: inval,
  });
  return { create, update, remove };
}
