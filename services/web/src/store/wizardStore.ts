import { create } from "zustand";
import { DiscoveredCamera } from "../hooks/useDiscovery";

export interface CameraSetupEntry {
  camera: DiscoveredCamera;
  name: string;
  username: string;
  password: string;
  recordContinuous: boolean;
  recordMotion: boolean;
}

interface WizardState {
  step: number;
  scanId: string | null;
  discoveredCameras: DiscoveredCamera[];
  selectedCameras: CameraSetupEntry[];
  goNext: () => void;
  goBack: () => void;
  setScanId: (id: string | null) => void;
  setDiscoveredCameras: (cameras: DiscoveredCamera[]) => void;
  toggleCameraSelection: (camera: DiscoveredCamera) => void;
  updateCredential: (cameraId: string, field: "username" | "password", value: string) => void;
  toggleRecordingType: (cameraId: string, type: "recordContinuous" | "recordMotion") => void;
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
    const exists = current.find((e) => e.camera.id === camera.id);
    if (exists) {
      set({ selectedCameras: current.filter((e) => e.camera.id !== camera.id) });
    } else {
      set({
        selectedCameras: [
          ...current,
          {
            camera,
            name: camera.name || `Camera ${camera.ip_address}`,
            username: "",
            password: "",
            recordContinuous: true,
            recordMotion: false,
          },
        ],
      });
    }
  },

  updateCredential: (cameraId, field, value) =>
    set((s) => ({
      selectedCameras: s.selectedCameras.map((e) =>
        e.camera.id === cameraId ? { ...e, [field]: value } : e
      ),
    })),

  toggleRecordingType: (cameraId, type) =>
    set((s) => ({
      selectedCameras: s.selectedCameras.map((e) =>
        e.camera.id === cameraId ? { ...e, [type]: !e[type] } : e
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
