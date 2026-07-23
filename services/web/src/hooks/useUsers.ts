import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "../api/client";
import type { UserRecord } from "../types/user";

export function useUsers(page = 1) {
  return useQuery({
    queryKey: ["users", page],
    queryFn: async () => {
      const res = await apiClient.get("/users", { params: { page, per_page: 25 } });
      return {
        data: (res.data?.data || []) as UserRecord[],
        metadata: res.data?.metadata || { page: 1, per_page: 25, total: 0 },
      };
    },
  });
}

export function useUserMutations() {
  const qc = useQueryClient();
  const inval = () => qc.invalidateQueries({ queryKey: ["users"] });

  const create = useMutation({
    mutationFn: (body: { username: string; password: string; role: string }) =>
      apiClient.post("/users", body),
    onSuccess: inval,
  });

  const update = useMutation({
    mutationFn: ({ id, ...body }: { id: string; role?: string; is_active?: boolean }) =>
      apiClient.patch(`/users/${id}`, body),
    onSuccess: inval,
  });

  const remove = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/users/${id}`),
    onSuccess: inval,
  });

  return { create, update, remove };
}
