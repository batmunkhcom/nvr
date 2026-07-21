import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCameras } from "../hooks/useCameras";
import apiClient from "../api/client";

vi.mock("../api/client", () => ({ default: { get: vi.fn() } }));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useCameras", () => {
  it("returns camera list from API", async () => {
    const mockCameras = [
      { id: "1", name: "Front Door", ip_address: "10.0.0.1", status: "online",
        port: 554, manufacturer: "Hikvision", model: "DS-2CD",
        stream_main_uri: "rtsp://10.0.0.1/", has_ptz: false, has_audio: false,
        created_at: "2026-01-01T00:00:00Z", updated_at: null },
    ];

    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { data: mockCameras } });

    const { result } = renderHook(() => useCameras(), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toEqual(mockCameras);
    });
  });

  it("returns empty array when API returns null", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {} });

    const { result } = renderHook(() => useCameras(), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toEqual([]);
    });
  });
});
