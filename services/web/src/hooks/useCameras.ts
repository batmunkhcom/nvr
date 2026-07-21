import { useQuery } from "@tanstack/react-query";
import apiClient from "../../api/client";
import { Camera } from "../../types/camera";

export function useCameras() {
  return useQuery({
    queryKey: ["cameras"],
    queryFn: async () => {
      const res = await apiClient.get("/cameras?per_page=100");
      return (res.data?.data || []) as Camera[];
    },
    refetchInterval: 30_000,
  });
}
