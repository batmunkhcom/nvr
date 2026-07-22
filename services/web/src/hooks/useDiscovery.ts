import type { DiscoveredDevice } from "../types/camera";
import { useCameraMutations } from "./useCameras";

export type DiscoveredCamera = DiscoveredDevice;

export { useDiscovery as useStartDiscovery } from "./useCameras";
export { useDiscoveryStatus } from "./useCameras";
export { useDiscoveryResults } from "./useCameras";

export function useAddCamera() {
  const { createCamera } = useCameraMutations();
  return createCamera;
}
