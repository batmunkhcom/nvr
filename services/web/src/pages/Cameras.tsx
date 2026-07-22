import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Wifi } from "lucide-react";
import { useCameras, useCameraMutations } from "../hooks/useCameras";
import type { Camera, TestResult } from "../types/camera";
import CameraAddDialog from "../components/camera/CameraAddDialog";
import CameraEditDialog from "../components/camera/CameraEditDialog";
import DiscoveryModal from "../components/camera/DiscoveryModal";

const statusColors: Record<string, string> = {
  online: "bg-green-500",
  offline: "bg-red-500",
  degraded: "bg-yellow-500",
  unknown: "bg-gray-500",
};

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    online: "Online",
    offline: "Offline",
    degraded: "Degraded",
    unknown: "Unknown",
  };
  return map[s] || s;
}

function errorLabel(errorCode: string | null | undefined, fallback: string): string {
  if (errorCode === "auth_failed") return `Authentication failed — ${fallback}`;
  return fallback;
}

export default function Cameras() {
  const { data: cameras, isLoading } = useCameras();
  const { deleteCamera, testCamera } = useCameraMutations();
  const navigate = useNavigate();
  const [showAdd, setShowAdd] = useState(false);
  const [editCam, setEditCam] = useState<Camera | null>(null);
  const [showDiscovery, setShowDiscovery] = useState(false);
  const [testingAll, setTestingAll] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, TestResult>>({});

  const handleTest = async (id: string) => {
    try {
      const result = await testCamera.mutateAsync(id);
      setTestResult((prev) => ({ ...prev, [id]: result }));
    } catch {
      // ignored
    }
  };

  const handleTestAll = async () => {
    if (!cameras?.length) return;
    setTestingAll(true);
    try {
      for (const cam of cameras) {
        try {
          const result = await testCamera.mutateAsync(cam.id);
          setTestResult((prev) => ({ ...prev, [cam.id]: result }));
        } catch {
          // continue with next camera
        }
      }
    } finally {
      setTestingAll(false);
    }
  };

  const handleDelete = async (cam: Camera) => {
    if (!confirm(`Delete "${cam.name}"? This cannot be undone.`)) return;
    deleteCamera.mutate(cam.id);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">Cameras</h1>
          {cameras && (
            <p className="text-sm text-gray-500 mt-0.5">
              {cameras.length} camera{cameras.length !== 1 ? "s" : ""} total
              {cameras.filter((c) => c.status === "online").length > 0 && (
                <span className="text-green-400 ml-2">
                  {cameras.filter((c) => c.status === "online").length} online
                </span>
              )}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleTestAll}
            disabled={testingAll || !cameras?.length}
            className="flex items-center gap-1.5 px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded text-sm text-white"
          >
            {testingAll ? "Testing..." : "Test All"}
          </button>
          <button
            onClick={() => setShowDiscovery(true)}
            className="flex items-center gap-1.5 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white"
          >
            <Wifi size={14} /> Scan Network
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm text-white"
          >
            + Add Camera
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-16 bg-gray-800 rounded border border-gray-700 animate-pulse"
            />
          ))}
        </div>
      )}

      {!isLoading && !cameras?.length && (
        <div className="bg-gray-900 rounded border border-gray-800 p-8 text-center">
          <p className="text-gray-500 mb-4">No cameras configured.</p>
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm text-white"
          >
            + Add Your First Camera
          </button>
        </div>
      )}

      {!isLoading && cameras && cameras.length > 0 && (
        <div className="space-y-1.5">
          {cameras.map((cam) => (
            <div
              key={cam.id}
              className="flex items-center gap-3 bg-gray-900 border border-gray-800 hover:border-gray-700 rounded px-4 py-3 transition-colors"
            >
              <span
                className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${statusColors[cam.status] || statusColors.unknown}`}
                title={statusLabel(cam.status)}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white truncate">
                    {cam.name}
                  </span>
                  {cam.manufacturer && (
                    <span className="text-xs bg-gray-800 px-1.5 py-0.5 rounded text-gray-400">
                      {cam.manufacturer}
                    </span>
                  )}
                  {cam.model && (
                    <span className="text-xs text-gray-600">{cam.model}</span>
                  )}
                  {(cam.location_name || cam.location) && (
                    <span className="text-xs bg-blue-900/40 text-blue-400 px-1.5 py-0.5 rounded border border-blue-800/50">
                      {cam.location_name || cam.location}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-500 mt-0.5">
                  <span>{cam.ip_address}</span>
                  {cam.stream_main_uri && (
                    <span className="font-mono text-gray-600 truncate">
                      {cam.stream_main_uri}
                    </span>
                  )}
                </div>
                {(() => {
                  const fresh = testResult[cam.id];
                  if (fresh?.error_message) {
                    return (
                      <div className="flex items-center gap-1.5 text-xs mt-1 text-red-400">
                        <AlertTriangle size={12} className="flex-shrink-0" />
                        <span>{errorLabel(fresh.error_code, fresh.error_message)}</span>
                      </div>
                    );
                  }
                  if (fresh) {
                    return (
                      <div className="flex items-center gap-2 text-xs mt-1">
                        <span className="text-green-400">
                          OK — stream authenticated
                          {fresh.latency_ms != null && ` (${fresh.latency_ms} ms)`}
                        </span>
                        {fresh.open_ports.length > 0 && (
                          <span className="text-gray-600">
                            Ports: {fresh.open_ports.join(", ")}
                          </span>
                        )}
                      </div>
                    );
                  }
                  if (cam.connection_error) {
                    return (
                      <div className="flex items-center gap-1.5 text-xs mt-1 text-red-400">
                        <AlertTriangle size={12} className="flex-shrink-0" />
                        <span>{cam.connection_error}</span>
                      </div>
                    );
                  }
                  return null;
                })()}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                {cam.has_ptz && (
                  <span className="text-[10px] bg-blue-900/50 text-blue-400 px-1 py-0.5 rounded">
                    PTZ
                  </span>
                )}
                {cam.has_audio && (
                  <span className="text-[10px] bg-purple-900/50 text-purple-400 px-1 py-0.5 rounded">
                    AUD
                  </span>
                )}
                {cam.has_onvif && (
                  <span className="text-[10px] bg-teal-900/50 text-teal-400 px-1 py-0.5 rounded">
                    ONVIF
                  </span>
                )}
                <button
                  onClick={() => navigate(`/live/${cam.id}`)}
                  title="Live View"
                  className="px-2 py-1 text-xs text-blue-400 hover:bg-gray-800 rounded"
                >
                  Live
                </button>
                <button
                  onClick={() => handleTest(cam.id)}
                  title="Test Connection"
                  className="px-2 py-1 text-xs text-gray-400 hover:bg-gray-800 rounded"
                >
                  Test
                </button>
                <button
                  onClick={() => setEditCam(cam)}
                  title="Edit"
                  className="px-2 py-1 text-xs text-gray-400 hover:bg-gray-800 rounded"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDelete(cam)}
                  title="Delete"
                  className="px-2 py-1 text-xs text-red-400 hover:bg-gray-800 rounded"
                >
                  Del
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <CameraAddDialog open={showAdd} onClose={() => setShowAdd(false)} />
      <CameraEditDialog
        open={!!editCam}
        onClose={() => setEditCam(null)}
        camera={editCam}
      />
      <DiscoveryModal open={showDiscovery} onClose={() => setShowDiscovery(false)} />
    </div>
  );
}
