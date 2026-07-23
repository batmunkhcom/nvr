import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useLocations, useLocationMutations } from "../hooks/useLocations";
import apiClient from "../api/client";

vi.mock("../api/client", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const mockLocations = [
  { id: "l1", name: "Office", description: null, camera_count: 2, created_at: null },
  { id: "l2", name: "Warehouse", description: "main", camera_count: 5, created_at: null },
];

describe("useLocations", () => {
  it("returns location list from API", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { data: mockLocations } });

    const { result } = renderHook(() => useLocations(), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toEqual(mockLocations);
    });
  });

  it("returns empty array when API returns no data", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {} });

    const { result } = renderHook(() => useLocations(), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toEqual([]);
    });
  });
});

describe("useLocationMutations", () => {
  it("createLocation posts to /locations", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { data: [] } });
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { data: mockLocations[0] } });

    const { result } = renderHook(() => useLocationMutations(), { wrapper });
    result.current.createLocation.mutate({ name: "Office" });

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith("/locations", { name: "Office" });
    });
  });

  it("updateLocation patches /locations/:id", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { data: [] } });
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: { data: mockLocations[0] } });

    const { result } = renderHook(() => useLocationMutations(), { wrapper });
    result.current.updateLocation.mutate({ id: "l1", name: "Renamed" });

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith("/locations/l1", { name: "Renamed" });
    });
  });

  it("deleteLocation deletes /locations/:id", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { data: [] } });
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: {} });

    const { result } = renderHook(() => useLocationMutations(), { wrapper });
    result.current.deleteLocation.mutate("l1");

    await waitFor(() => {
      expect(apiClient.delete).toHaveBeenCalledWith("/locations/l1");
    });
  });
});
