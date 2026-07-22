import { useNavigate } from "react-router-dom";
import { useCameras } from "../../hooks/useCameras";
import { Camera } from "../../types/camera";
import { Play } from "lucide-react";

const statusColors: Record<string, string> = {
  online: "bg-green-500",
  offline: "bg-red-500",
  degraded: "bg-yellow-500",
  unknown: "bg-gray-500",
};

function CameraTile({ camera }: { camera: Camera }) {
  const navigate = useNavigate();
  const dot = statusColors[camera.status] || statusColors.unknown;
  const isLive = camera.status === "online";

  return (
    <div
      onClick={() => navigate(`/live/${camera.id}`)}
      className="aspect-video bg-gray-800 rounded border border-gray-700 relative group overflow-hidden cursor-pointer hover:border-gray-500 transition-colors"
    >
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
        <span className="text-gray-500 text-4xl font-light">{camera.name.charAt(0).toUpperCase()}</span>
        <span className="text-gray-600 text-xs">{camera.name}</span>
      </div>

      <div className="absolute top-2 left-2 flex items-center gap-1.5">
        <span className={`w-2.5 h-2.5 rounded-full ${dot} ${isLive ? "animate-pulse" : ""}`} />
        <span className="text-xs text-gray-400">{camera.status}</span>
      </div>

      {isLive && (
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="flex items-center gap-1 px-2 py-0.5 bg-green-700 rounded text-xs text-white">
            <Play size={10} /> Live
          </span>
        </div>
      )}

      <div className="absolute bottom-2 left-2 right-2 flex justify-between items-center opacity-0 group-hover:opacity-100 transition-opacity">
        <span className="text-xs text-gray-400 truncate">{camera.ip_address}</span>
        {camera.has_ptz && <span className="text-xs bg-blue-700 px-1.5 py-0.5 rounded text-white">PTZ</span>}
      </div>
    </div>
  );
}

export default function CameraGrid() {
  const { data: cameras, isLoading } = useCameras();

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="aspect-video bg-gray-800 rounded border border-gray-700 animate-pulse" />
        ))}
      </div>
    );
  }

  if (!cameras?.length) {
    return (
      <div className="bg-gray-900 rounded border border-gray-800 p-8 text-center text-gray-500">
        No cameras configured. Go to Cameras to add one.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      {cameras.map((camera) => (
        <CameraTile key={camera.id} camera={camera} />
      ))}
    </div>
  );
}
