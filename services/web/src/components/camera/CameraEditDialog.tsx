import { useEffect, useState, type FormEvent } from "react";
import { useCameraMutations } from "../../hooks/useCameras";
import type { Camera } from "../../types/camera";

interface Props {
  open: boolean;
  onClose: () => void;
  camera: Camera | null;
}

export default function CameraEditDialog({ open, onClose, camera }: Props) {
  const { updateCamera } = useCameraMutations();
  const [name, setName] = useState("");
  const [ip, setIp] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [streamMain, setStreamMain] = useState("");
  const [streamSub, setStreamSub] = useState("");
  const [recordingMode, setRecordingMode] = useState("continuous");
  const [isActive, setIsActive] = useState(true);
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (camera) {
      setName(camera.name);
      setIp(camera.ip_address);
      setUsername(camera.username);
      setPassword("");
      setStreamMain(camera.stream_main_uri || "");
      setStreamSub(camera.stream_sub_uri || "");
      setRecordingMode(camera.recording_mode || "continuous");
      setIsActive(camera.status !== "offline");
      setLocation(camera.location || "");
      setNotes(camera.notes || "");
    }
  }, [camera]);

  if (!open || !camera) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !ip.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      await updateCamera.mutateAsync({
        id: camera.id,
        name: name.trim(),
        ip_address: ip.trim(),
        username: username || "admin",
        password: password || undefined,
        stream_main_uri: streamMain || undefined,
        stream_sub_uri: streamSub || undefined,
        recording_mode: recordingMode,
        is_active: isActive,
        location: location || undefined,
        notes: notes || undefined,
      });
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Edit Camera</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl leading-none">
            &times;
          </button>
        </div>

        {error && (
          <div className="bg-red-900/40 border border-red-800 rounded px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Name *</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">IP Address *</label>
              <input
                type="text"
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                required
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Leave blank to keep current"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Main Stream URI</label>
            <input
              type="text"
              value={streamMain}
              onChange={(e) => setStreamMain(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Sub Stream URI</label>
            <input
              type="text"
              value={streamSub}
              onChange={(e) => setStreamSub(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none font-mono"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Recording Mode</label>
              <select
                value={recordingMode}
                onChange={(e) => setRecordingMode(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              >
                <option value="continuous">Continuous</option>
                <option value="motion">Motion only</option>
                <option value="never">Never</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Active</label>
              <label className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  className="rounded border-gray-600 bg-gray-800 text-blue-600"
                />
                <span className="text-sm text-gray-300">Enabled</span>
              </label>
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Location</label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Front Gate"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
            />
          </div>
          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm text-white"
            >
              {submitting ? "Saving..." : "Save Changes"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-200"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
