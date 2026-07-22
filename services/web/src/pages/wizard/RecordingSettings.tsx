import { useWizardStore } from "../../store/wizardStore";
import { Camera } from "lucide-react";

export default function WizardRecordingSettings() {
  const { selectedCameras, toggleRecordingType, goNext, goBack } = useWizardStore();

  return (
    <div className="max-w-2xl mx-auto mt-8">
      <h2 className="text-2xl font-bold mb-2">Recording Settings</h2>
      <p className="text-gray-400 mb-6">Choose recording modes for each camera.</p>

      <div className="space-y-4">
        {selectedCameras.map((entry) => (
          <div key={entry.camera.ip_address} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <div className="flex items-center gap-2 mb-3">
              <Camera size={16} className="text-gray-500" />
              <p className="text-sm font-semibold">
                {entry.camera.manufacturer || "Camera"} {entry.camera.ip_address}
              </p>
            </div>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={entry.recordContinuous}
                  onChange={() => toggleRecordingType(entry.camera.ip_address, "recordContinuous")}
                  className="h-4 w-4"
                />
                <div>
                  <p className="text-sm text-gray-300">Continuous Recording</p>
                  <p className="text-xs text-gray-500">Record 24/7</p>
                </div>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={entry.recordMotion}
                  onChange={() => toggleRecordingType(entry.camera.ip_address, "recordMotion")}
                  className="h-4 w-4"
                />
                <div>
                  <p className="text-sm text-gray-300">Motion Recording</p>
                  <p className="text-xs text-gray-500">Record only when motion detected</p>
                </div>
              </label>
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-3 mt-6">
        <button onClick={goBack} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300">Back</button>
        <button onClick={goNext} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white">Review &amp; Add Cameras</button>
      </div>
    </div>
  );
}
