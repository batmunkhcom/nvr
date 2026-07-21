import { useCameras } from "../hooks/useCameras";
import { Camera } from "../types/camera";

const statusColors: Record<string, string> = {
  online: "bg-green-500",
  offline: "bg-red-500",
  degraded: "bg-yellow-500",
  unknown: "bg-gray-500",
};

function CameraTile({ camera }: { camera: Camera }) {
  const dot = statusColors[camera.status] || statusColors.unknown;
  return (
    <div className="aspect-video bg-gray-800 rounded border border-gray-700 relative group overflow-hidden">
      <div className="absolute inset-0 flex items-center justify-center text-gray-600 text-sm">
        {camera.name}
      </div>
      <div className="absolute top-2 left-2 flex items-center gap-1.5">
        <span className={`w-2.5 h-2.5 rounded-full ${dot}`} />
        <span className="text-xs text-gray-400">{camera.status}</span>
      </div>
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
