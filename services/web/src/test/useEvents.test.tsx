import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEvents, useAcknowledgeEvent } from "../hooks/useEvents";
import apiClient from "../api/client";

vi.mock("../api/client", () => ({
  default: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useEvents", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches events from API", async () => {
    const mockEvents = [
      { id: "1", camera_id: "cam1", event_type: "motion_detected", severity: "warning",
        start_time: "2026-01-01T00:00:00Z", end_time: null, metadata: {}, is_acknowledged: false,
        created_at: "2026-01-01T00:00:00Z" },
    ];

    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { data: mockEvents } });

    const { result } = renderHook(() => useEvents(), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toEqual(mockEvents);
    });
  });

  it("handles empty response", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { data: [] } });

    const { result } = renderHook(() => useEvents(), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toEqual([]);
    });
  });

  it("passes filters to query params", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { data: [] } });

    renderHook(() => useEvents({ event_type: "motion" }), { wrapper });

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith("/events", {
        params: { per_page: 50, event_type: "motion" },
      });
    });
  });
});

describe("useAcknowledgeEvent", () => {
  it("calls acknowledge endpoint", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({});

    const { result } = renderHook(() => useAcknowledgeEvent(), { wrapper });

    await result.current.mutateAsync("evt1");

    expect(apiClient.patch).toHaveBeenCalledWith("/events/evt1/acknowledge");
  });
});
