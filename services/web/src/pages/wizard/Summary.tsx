import { useWizardStore } from "../../store/wizardStore";
import { useAddCamera } from "../../hooks/useDiscovery";
import { useNavigate } from "react-router-dom";
import { CheckCircle, Loader2, XCircle, Camera } from "lucide-react";
import { useState } from "react";

export default function WizardSummary() {
  const { selectedCameras, goBack, reset } = useWizardStore();
  const addCamera = useAddCamera();
  const navigate = useNavigate();
  const [addedIds, setAddedIds] = useState<Set<string>>(new Set());
  const [failed, setFailed] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [done, setDone] = useState(false);

  const handleAddAll = async () => {
    if (adding) return;
    setAdding(true);
    for (const entry of selectedCameras) {
      try {
        await addCamera.mutateAsync({
          name: entry.camera.name || `Camera ${entry.camera.ip_address}`,
          ip_address: entry.camera.ip_address,
          username: entry.username || undefined,
          password: entry.password || undefined,
          rtsp_uri: entry.camera.rtsp_uri || undefined,
        });
        setAddedIds((s) => new Set(s).add(entry.camera.id));
      } catch {
        setFailed((s) => new Set(s).add(entry.camera.id));
      }
    }
    setDone(true);
    setAdding(false);
  };

  return (
    <div className="max-w-2xl mx-auto mt-8">
      <h2 className="text-2xl font-bold mb-2">Summary</h2>
      <p className="text-gray-400 mb-6">Review and add your cameras to the NVR system.</p>

      <div className="space-y-2 mb-6">
        {selectedCameras.map((entry) => (
          <div key={entry.camera.id} className="flex items-center gap-3 p-3 bg-gray-900 rounded-lg border border-gray-800">
            {addedIds.has(entry.camera.id) ? (
              <CheckCircle size={18} className="text-green-400" />
            ) : failed.has(entry.camera.id) ? (
              <XCircle size={18} className="text-red-400" />
            ) : adding ? (
              <Loader2 size={18} className="text-blue-400 animate-spin" />
            ) : (
              <Camera size={18} className="text-gray-500" />
            )}
            <div className="flex-1">
              <p className="text-sm font-medium">{entry.camera.name || `Camera ${entry.camera.ip_address}`}</p>
              <p className="text-xs text-gray-500">
                {entry.camera.ip_address} &middot; {entry.recordContinuous ? "Continuous" : ""}{entry.recordMotion ? " Motion" : ""}
                {entry.username ? ` &middot; ${entry.username}` : ""}
              </p>
            </div>
          </div>
        ))}
      </div>

      {!done && !adding && (
        <div className="flex gap-3">
          <button onClick={goBack} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300">Back</button>
          <button onClick={handleAddAll} className="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium text-white">
            Add {selectedCameras.length} Camera{selectedCameras.length !== 1 ? "s" : ""}
          </button>
        </div>
      )}

      {adding && (
        <div className="flex items-center gap-3 text-blue-400">
          <Loader2 size={20} className="animate-spin" />
          <p className="text-sm">Adding cameras, please wait...</p>
        </div>
      )}

      {done && (
        <div className="flex gap-3">
          <button
            onClick={() => { reset(); navigate("/dashboard"); }}
            className="px-6 py-2 bg-green-600 hover:bg-green-700 rounded-lg font-medium text-white"
          >
            Go to Dashboard
          </button>
          <button
            onClick={() => { reset(); navigate("/cameras"); }}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
          >
            View All Cameras
          </button>
        </div>
      )}
    </div>
  );
}
