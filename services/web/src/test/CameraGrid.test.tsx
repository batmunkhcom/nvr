import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CameraGrid from "../components/camera/CameraGrid";
import apiClient from "../api/client";

vi.mock("../api/client", () => ({
  default: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
}));

vi.mock("../components/camera/MiniLivePreview", () => ({
  default: () => <div data-testid="mini-live-preview" />,
}));

function renderGrid() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <CameraGrid />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

const onlineCamera = {
  id: "c1",
  name: "Front Door",
  ip_address: "10.0.0.1",
  status: "online",
  port: 554,
  manufacturer: "Hikvision",
  model: "DS-2CD",
  stream_main_uri: "rtsp://10.0.0.1/",
  has_ptz: true,
  has_audio: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
};

function mockApi(uiConfig: Record<string, unknown> = {}, cameras = [onlineCamera]) {
  vi.mocked(apiClient.get).mockImplementation((url: string) => {
    if (url.startsWith("/cameras")) return Promise.resolve({ data: { data: cameras } });
    if (url === "/system/ui-config") return Promise.resolve({ data: { data: uiConfig } });
    return Promise.resolve({ data: {} });
  });
  vi.mocked(apiClient.patch).mockResolvedValue({ data: { data: {} } });
}

describe("CameraGrid", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders camera tile with status and IP for online camera", async () => {
    mockApi();
    renderGrid();

    await waitFor(() => {
      expect(screen.getByText("Front Door")).toBeInTheDocument();
    });
    expect(screen.getByText("(cam1)")).toBeInTheDocument();
    expect(screen.getByText("10.0.0.1")).toBeInTheDocument();
  });

  it("mounts MiniLivePreview for online cameras", async () => {
    mockApi();
    renderGrid();

    await waitFor(() => {
      expect(screen.getByTestId("mini-live-preview")).toBeInTheDocument();
    });
  });

  it("shows name placeholder instead of preview for offline cameras", async () => {
    mockApi({}, [{ ...onlineCamera, status: "offline" }]);
    renderGrid();

    await waitFor(() => {
      // name appears in both placeholder and top badge
      expect(screen.getAllByText("Front Door").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getByText("F")).toBeInTheDocument();
    expect(screen.queryByTestId("mini-live-preview")).not.toBeInTheDocument();
  });

  it("defaults to 2 columns and switches on selector click", async () => {
    mockApi();
    const { container } = renderGrid();

    // wait for real data (skeleton also has grid-cols-2)
    await waitFor(() => {
      expect(screen.getByText("Front Door")).toBeInTheDocument();
    });
    expect(container.querySelector(".grid-cols-2")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("4 columns"));

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith("/system/ui-config", {
        key: "ui.dashboard_columns",
        value: 4,
      });
    });
  });

  it("reads persisted column count from ui-config", async () => {
    mockApi({ "ui.dashboard_columns": 3 });
    const { container } = renderGrid();

    await waitFor(() => {
      expect(screen.getByText("Front Door")).toBeInTheDocument();
    });
    expect(container.querySelector(".grid-cols-3")).toBeInTheDocument();
  });

  it("shows empty state when no cameras", async () => {
    mockApi({}, []);
    renderGrid();

    await waitFor(() => {
      expect(screen.getByText(/No cameras configured/)).toBeInTheDocument();
    });
  });
});
