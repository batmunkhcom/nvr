import { useState, useEffect, useCallback, type FormEvent } from "react";
import { Video, VideoOff, X } from "lucide-react";
import apiClient from "../../api/client";

export default function PauseAllButton() {
  const [paused, setPaused] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await apiClient.get("/system/recording/status");
      setPaused(r.data?.data?.paused ?? false);
    } catch {}
  }, []);

  useEffect(() => {
    fetchStatus();
    const timer = setInterval(fetchStatus, 5000);
    return () => clearInterval(timer);
  }, [fetchStatus]);

  const handleToggle = async (e?: FormEvent) => {
    if (e) e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const endpoint = paused
        ? "/system/recording/resume"
        : "/system/recording/pause";
      await apiClient.post(endpoint, { admin_password: password });
      setPaused(!paused);
      setPassword("");
      setModalOpen(false);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || "Failed to toggle recording";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const closeModal = () => {
    setModalOpen(false);
    setPassword("");
    setError("");
  };

  return (
    <>
      <button
        onClick={() => setModalOpen(true)}
        className="p-1.5 rounded-full hover:bg-gray-800 transition-colors"
        title={paused ? "Реcording Paused — Click to Resume" : "Recording Active — Click to Pause All"}
      >
        {paused ? (
          <VideoOff size={18} className="text-red-500 animate-pulse-recording" />
        ) : (
          <Video size={18} className="text-green-500 animate-pulse-recording" />
        )}
      </button>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={closeModal}>
          <div
            className="bg-gray-800 border border-gray-700 rounded-lg shadow-2xl w-80 p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                {paused ? (
                  <VideoOff size={20} className="text-red-500" />
                ) : (
                  <Video size={20} className="text-green-500" />
                )}
                <span className="text-sm font-medium text-gray-200">
                  {paused ? "Resume All Recordings" : "Pause All Recordings"}
                </span>
              </div>
              <button onClick={closeModal} className="text-gray-500 hover:text-gray-300">
                <X size={16} />
              </button>
            </div>

            <p className="text-xs text-gray-400 mb-4">
              {paused
                ? "All cameras will resume recording."
                : "All cameras will stop recording immediately. Streaming remains available."}
            </p>

            <form onSubmit={handleToggle} className="space-y-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Admin Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); setError(""); }}
                  className="w-full px-3 py-2 text-sm bg-gray-900 border border-gray-600 rounded text-gray-200 focus:outline-none focus:border-blue-500"
                  placeholder="Enter your admin password"
                  autoFocus
                />
              </div>

              {error && <p className="text-xs text-red-400">{error}</p>}

              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={closeModal}
                  className="flex-1 px-3 py-2 text-xs text-gray-400 bg-gray-700 rounded hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!password || loading}
                  className={`flex-1 px-3 py-2 text-xs font-medium rounded text-white disabled:opacity-40 ${
                    paused ? "bg-green-600 hover:bg-green-500" : "bg-red-600 hover:bg-red-500"
                  }`}
                >
                  {loading ? "..." : paused ? "Resume" : "Pause All"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
