import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Cameras from "../pages/Cameras";
import apiClient from "../api/client";
import type { Camera } from "../types/camera";

vi.mock("../api/client", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("../components/camera/CameraAddDialog", () => ({ default: () => null }));
vi.mock("../components/camera/CameraEditDialog", () => ({ default: () => null }));
vi.mock("../components/camera/DiscoveryModal", () => ({ default: () => null }));

const baseCamera = {
  id: "c1",
  name: "Gate Cam",
  ip_address: "10.0.0.5",
  status: "degraded",
  port: 554,
  manufacturer: "Hikvision",
  model: "DS-2CD",
  stream_main_uri: "rtsp://10.0.0.5/",
  has_ptz: false,
  has_audio: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
} as unknown as Camera;

function renderPage(cameras = [baseCamera]) {
  vi.mocked(apiClient.get).mockImplementation((url: string) => {
    if (url.startsWith("/cameras")) return Promise.resolve({ data: { data: cameras } });
    return Promise.resolve({ data: { data: [] } });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Cameras />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

describe("Cameras page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders connection_error badge from DB", async () => {
    renderPage([
      { ...baseCamera, connection_error: "Wrong username or password (RTSP 401)" },
    ]);

    await waitFor(() => {
      expect(
        screen.getByText("Wrong username or password (RTSP 401)")
      ).toBeInTheDocument();
    });
  });

  it("does not render error badge when connection_error is null", async () => {
    renderPage([{ ...baseCamera, connection_error: null }]);

    await waitFor(() => {
      expect(screen.getByText("Gate Cam")).toBeInTheDocument();
    });
    expect(screen.queryByText(/401/)).not.toBeInTheDocument();
  });

  it("Test All calls test endpoint for every camera", async () => {
    const cams = [
      baseCamera,
      { ...baseCamera, id: "c2", name: "Yard Cam" },
      { ...baseCamera, id: "c3", name: "Door Cam" },
    ];
    renderPage(cams);
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { data: { auth_ok: true, error_code: null, error_message: null, latency_ms: 5, open_ports: [] } },
    });

    await waitFor(() => {
      expect(screen.getByText("Gate Cam")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Test All"));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith("/cameras/c1/test");
      expect(apiClient.post).toHaveBeenCalledWith("/cameras/c2/test");
      expect(apiClient.post).toHaveBeenCalledWith("/cameras/c3/test");
    });
  });

  it("shows auth failure label after individual test", async () => {
    renderPage();
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        data: {
          auth_ok: false,
          error_code: "auth_failed",
          error_message: "Wrong username or password",
          latency_ms: null,
          open_ports: [554],
        },
      },
    });

    await waitFor(() => {
      expect(screen.getByText("Gate Cam")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Test All"));

    await waitFor(() => {
      expect(screen.getByText(/Authentication failed/)).toBeInTheDocument();
    });
  });

  it("shows location badge when location_name is set", async () => {
    renderPage([{ ...baseCamera, location_name: "Office" }]);

    await waitFor(() => {
      expect(screen.getByText("Office")).toBeInTheDocument();
    });
  });

  it("Test All disabled when no cameras", async () => {
    renderPage([]);

    await waitFor(() => {
      expect(screen.getByText(/No cameras configured/)).toBeInTheDocument();
    });
    expect(screen.getByText("Test All")).toBeDisabled();
  });
});
