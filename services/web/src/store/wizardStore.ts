import { create } from "zustand";
import type { DiscoveredDevice } from "../types/camera";

export interface CameraSetupEntry {
  camera: DiscoveredDevice;
  name: string;
  username: string;
  password: string;
  recordContinuous: boolean;
  recordMotion: boolean;
}

interface WizardState {
  step: number;
  scanId: string | null;
  discoveredCameras: DiscoveredDevice[];
  selectedCameras: CameraSetupEntry[];
  goNext: () => void;
  goBack: () => void;
  setScanId: (id: string | null) => void;
  setDiscoveredCameras: (cameras: DiscoveredDevice[]) => void;
  toggleCameraSelection: (camera: DiscoveredDevice) => void;
  updateCredential: (ip: string, field: "username" | "password", value: string) => void;
  toggleRecordingType: (ip: string, type: "recordContinuous" | "recordMotion") => void;
  reset: () => void;
}

export const useWizardStore = create<WizardState>((set, get) => ({
  step: 0,
  scanId: null,
  discoveredCameras: [],
  selectedCameras: [],

  goNext: () => set((s) => ({ step: Math.min(s.step + 1, 5) })),
  goBack: () => set((s) => ({ step: Math.max(s.step - 1, 0) })),
  setScanId: (id) => set({ scanId: id }),
  setDiscoveredCameras: (cameras) => set({ discoveredCameras: cameras }),

  toggleCameraSelection: (camera) => {
    const current = get().selectedCameras;
    const exists = current.find((e) => e.camera.ip_address === camera.ip_address);
    if (exists) {
      set({ selectedCameras: current.filter((e) => e.camera.ip_address !== camera.ip_address) });
    } else {
      const autoName = camera.manufacturer
        ? `${camera.manufacturer} ${camera.ip_address}`
        : `Camera ${camera.ip_address}`;
      set({
        selectedCameras: [
          ...current,
          {
            camera,
            name: autoName,
            username: "admin",
            password: "",
            recordContinuous: true,
            recordMotion: false,
          },
        ],
      });
    }
  },

  updateCredential: (ip, field, value) =>
    set((s) => ({
      selectedCameras: s.selectedCameras.map((e) =>
        e.camera.ip_address === ip ? { ...e, [field]: value } : e
      ),
    })),

  toggleRecordingType: (ip, type) =>
    set((s) => ({
      selectedCameras: s.selectedCameras.map((e) =>
        e.camera.ip_address === ip ? { ...e, [type]: !e[type] } : e
      ),
    })),

  reset: () =>
    set({
      step: 0,
      scanId: null,
      discoveredCameras: [],
      selectedCameras: [],
    }),
}));
