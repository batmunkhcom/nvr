import { useParams, useNavigate } from "react-router-dom";
import { useCameras } from "../hooks/useCameras";
import { ArrowLeft, Maximize, Minimize, Camera } from "lucide-react";
import { useState, useCallback } from "react";
import { Camera as CameraType } from "../types/camera";

export default function LiveView() {
  const params = useParams();
  const navigate = useNavigate();
  const { data: cameras } = useCameras();
  const camera = (cameras || []).find((c: CameraType) => c.id === params.cameraId);
  const [fullscreen, setFullscreen] = useState(false);

  const toggleFullscreen = useCallback(() => {
    setFullscreen((f) => !f);
  }, []);

  if (!camera) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500">Camera not found</p>
      </div>
    );
  }

  return (
    <div className={fullscreen ? "fixed inset-0 z-50 bg-black" : ""}>
      {!fullscreen && (
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={() => navigate(-1)}
            className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded text-gray-400"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-xl font-bold">{camera.name}</h1>
            <p className="text-xs text-gray-500">{camera.ip_address} &middot; {camera.status}</p>
          </div>
        </div>
      )}

      <div className={`relative bg-black rounded-lg overflow-hidden ${fullscreen ? "h-full" : "aspect-video"}`}>
        <div className="absolute inset-0 flex items-center justify-center">
          <Camera size={48} className="text-gray-700" />
          <p className="ml-3 text-gray-500 text-sm">{camera.name} — Live stream placeholder</p>
        </div>

        <button
          onClick={toggleFullscreen}
          className="absolute bottom-4 right-4 p-2 bg-black/50 hover:bg-black/70 rounded text-white z-10"
        >
          {fullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
        </button>

        <div className="absolute top-4 right-4 flex gap-2 z-10">
          <span
            className={`px-2 py-0.5 rounded text-xs font-mono ${
              camera.status === "online" ? "bg-green-700 text-green-200" : "bg-red-700 text-red-200"
            }`}
          >
            {camera.status}
          </span>
        </div>
      </div>
    </div>
  );
}
