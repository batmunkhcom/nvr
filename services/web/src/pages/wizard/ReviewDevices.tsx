import { useWizardStore } from "../../store/wizardStore";
import { Wifi, Camera } from "lucide-react";

export default function WizardReview() {
  const { discoveredCameras, selectedCameras, toggleCameraSelection, goNext, goBack } = useWizardStore();

  if (!discoveredCameras.length) {
    return (
      <div className="max-w-xl mx-auto mt-12 text-center">
        <Wifi size={48} className="mx-auto mb-4 text-gray-600" />
        <h2 className="text-2xl font-bold mb-2">No Cameras Found</h2>
        <p className="text-gray-400 mb-6">No cameras were detected on your network.</p>
        <div className="flex gap-3 justify-center">
          <button onClick={goBack} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300">Back</button>
          <button onClick={goNext} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white">Skip — Add Manually</button>
        </div>
      </div>
    );
  }

  const selected = new Set(selectedCameras.map((s) => s.camera.id));

  return (
    <div className="max-w-2xl mx-auto mt-8">
      <h2 className="text-2xl font-bold mb-2">Select Cameras</h2>
      <p className="text-gray-400 mb-1">{discoveredCameras.length} cameras found</p>
      <p className="text-sm text-gray-500 mb-6">Select the cameras you want to add to your NVR system.</p>

      <div className="space-y-2">
        {discoveredCameras.map((cam) => {
          const isSelected = selected.has(cam.id);
          return (
            <div
              key={cam.id}
              onClick={() => toggleCameraSelection(cam)}
              className={`flex items-center gap-4 p-3 rounded-lg border cursor-pointer transition-colors ${
                isSelected
                  ? "bg-blue-900/30 border-blue-700"
                  : "bg-gray-900 border-gray-800 hover:border-gray-700"
              }`}
            >
              <input type="checkbox" checked={isSelected} onChange={() => {}} className="h-4 w-4" />
              <Camera size={20} className="text-gray-500" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {cam.name || cam.manufacturer || "Unknown Camera"}
                </p>
                <p className="text-xs text-gray-500">
                  {cam.ip_address}:{cam.port} &middot; {cam.manufacturer} &middot; {Math.round(cam.confidence)}% confidence
                </p>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex gap-3 mt-6">
        <button onClick={goBack} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300">Back</button>
        <button onClick={goNext} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white">
          Configure Selected ({selectedCameras.length})
        </button>
      </div>
    </div>
  );
}
