import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "../api/client";

export interface Profile {
  id: string;
  username: string;
  email: string | null;
  role: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: async () => {
      const res = await apiClient.get("/auth/me");
      return res.data as Profile;
    },
    staleTime: 60_000,
  });
}

export function useProfileMutations() {
  const qc = useQueryClient();

  const updateProfile = useMutation({
    mutationFn: (body: { email: string | null }) => apiClient.patch("/auth/me", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profile"] }),
  });

  const changePassword = useMutation({
    mutationFn: (body: { old_password: string; new_password: string }) =>
      apiClient.post("/auth/change-password", body),
  });

  return { updateProfile, changePassword };
}
