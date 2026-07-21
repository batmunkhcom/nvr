import CameraGrid from "../components/camera/CameraGrid";
import { useCameras } from "../hooks/useCameras";

export default function Dashboard() {
  const { data: cameras } = useCameras();
  const online = cameras?.filter((c) => c.status === "online").length ?? 0;
  const total = cameras?.length ?? 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex gap-4 text-sm text-gray-400">
          <span>
            <span className="text-green-400 font-medium">{online}</span>/{total} online
          </span>
        </div>
      </div>
      <CameraGrid />
    </div>
  );
}
