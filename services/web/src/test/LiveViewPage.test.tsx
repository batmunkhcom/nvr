import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LiveViewPage from "../pages/LiveViewPage";
import apiClient from "../api/client";

vi.mock("../api/client", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock("hls.js", () => {
  class MockHls {
    static isSupported() {
      return true;
    }
    static Events = { ERROR: "hlsError", MANIFEST_PARSED: "hlsManifestParsed" };
    static ErrorTypes = { NETWORK_ERROR: "networkError" };
    loadSource() {}
    attachMedia() {}
    on() {}
    destroy() {}
  }
  return { default: MockHls };
});

const ptzCamera = {
  id: "c1",
  name: "PTZ Cam",
  ip_address: "10.0.0.9",
  status: "online",
  port: 554,
  manufacturer: "Dahua",
  model: "IPC",
  stream_main_uri: "rtsp://10.0.0.9/",
  has_ptz: true,
  has_audio: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
};

function renderPage(camera = ptzCamera) {
  vi.mocked(apiClient.get).mockImplementation((url: string) => {
    if (url.startsWith("/cameras?")) return Promise.resolve({ data: { data: [camera] } });
    if (url.includes("/live/status"))
      return Promise.resolve({ data: { data: { running: true } } });
    return Promise.resolve({ data: {} });
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/live/${camera.id}`]}>
        <Routes>
          <Route path="/live/:cameraId" element={<LiveViewPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("LiveViewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows camera name in header", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { data: { hls_url: "/hls/c1/index.m3u8" } },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("PTZ Cam")).toBeInTheDocument();
    });
  });

  it("starts stream and shows PTZ controls when playing", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { data: { hls_url: "/hls/c1/index.m3u8" } },
    });
    renderPage();

    await waitFor(
      () => {
        expect(screen.getByTitle("Pan Left")).toBeInTheDocument();
      },
      { timeout: 5000 }
    );
    expect(screen.getByTitle("Zoom In")).toBeInTheDocument();
    expect(screen.getByTitle("Zoom Out")).toBeInTheDocument();
  });

  it("PTZ button calls ptz API with direction", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { data: { hls_url: "/hls/c1/index.m3u8" } },
    });
    renderPage();

    await waitFor(
      () => {
        expect(screen.getByTitle("Pan Left")).toBeInTheDocument();
      },
      { timeout: 5000 }
    );

    fireEvent.click(screen.getByTitle("Pan Left"));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/cameras/c1/ptz",
        null,
        expect.objectContaining({ params: expect.objectContaining({ direction: "left" }) })
      );
    });
  });

  it("zoom button calls ptz API with zoom action", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { data: { hls_url: "/hls/c1/index.m3u8" } },
    });
    renderPage();

    await waitFor(
      () => {
        expect(screen.getByTitle("Zoom In")).toBeInTheDocument();
      },
      { timeout: 5000 }
    );

    fireEvent.click(screen.getByTitle("Zoom In"));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/cameras/c1/ptz",
        null,
        expect.objectContaining({ params: expect.objectContaining({ action: "zoom", zoom: "in" }) })
      );
    });
  });

  it("shows error state when camera has no stream configured", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { data: { hls_url: null, error: "Camera has no stream URI configured" } },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/no stream/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Retry/i)).toBeInTheDocument();
  });

  it("shows error state when live/start request fails", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new Error("network down"));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Failed to start stream/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Retry/i)).toBeInTheDocument();
  });

  it("shows 'Camera not found' for unknown id", () => {
    vi.mocked(apiClient.get).mockImplementation((url: string) => {
      if (url.startsWith("/cameras?")) return Promise.resolve({ data: { data: [] } });
      return Promise.resolve({ data: {} });
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/live/unknown-id"]}>
          <Routes>
            <Route path="/live/:cameraId" element={<LiveViewPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    return waitFor(() => {
      expect(screen.getByText("Camera not found")).toBeInTheDocument();
    });
  });
});
