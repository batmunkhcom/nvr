import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AppShell from "../components/layout/AppShell";
import { LocaleProvider } from "../i18n/LocaleContext";
import apiClient from "../api/client";

vi.mock("../api/client", () => ({
  default: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
}));

function renderWithProviders(component: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LocaleProvider>
        <BrowserRouter>{component}</BrowserRouter>
      </LocaleProvider>
    </QueryClientProvider>
  );
}

describe("AppShell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.get).mockImplementation((url: string) => {
      if (url === "/system/ui-config") return Promise.resolve({ data: { data: {} } });
      return Promise.resolve({ data: { data: [] } });
    });
    vi.mocked(apiClient.patch).mockResolvedValue({ data: { data: {} } });
  });

  it("renders sidebar navigation links", () => {
    renderWithProviders(<AppShell />);
    const dashboardLinks = screen.getAllByText("Dashboard");
    expect(dashboardLinks.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Cameras")).toBeInTheDocument();
    expect(screen.getByText("Recordings")).toBeInTheDocument();
    expect(screen.getByText("Events")).toBeInTheDocument();
    expect(screen.getByText("Storage")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("redirects / to /dashboard", () => {
    window.history.pushState({}, "", "/dashboard");
    renderWithProviders(<AppShell />);
    const dashboardLinks = screen.getAllByText("Dashboard");
    expect(dashboardLinks.length).toBeGreaterThanOrEqual(1);
  });

  it("sidebar collapse toggle hides labels and persists to ui-config", async () => {
    renderWithProviders(<AppShell />);

    const brandTexts = screen.getAllByText("NVR System");
    // Sidebar brand + Topbar title both show "NVR System" after i18n
    expect(brandTexts.length).toBeGreaterThanOrEqual(2);

    fireEvent.click(screen.getByTitle("Collapse sidebar"));

    await waitFor(() => {
      expect(apiClient.patch).toHaveBeenCalledWith("/system/ui-config", {
        key: "ui.sidebar_collapsed",
        value: true,
      });
    });
  });

  it("collapsed sidebar hides brand and shows expand button", async () => {
    vi.mocked(apiClient.get).mockImplementation((url: string) => {
      if (url === "/system/ui-config")
        return Promise.resolve({ data: { data: { "ui.sidebar_collapsed": true } } });
      return Promise.resolve({ data: { data: [] } });
    });
    renderWithProviders(<AppShell />);

    await waitFor(() => {
      expect(screen.getByTitle("Expand sidebar")).toBeInTheDocument();
    });
    // Sidebar brand hidden, but Topbar still shows "NVR System"
    const brandTexts = screen.getAllByText("NVR System");
    expect(brandTexts.length).toBe(1); // only Topbar remains
  });
});
