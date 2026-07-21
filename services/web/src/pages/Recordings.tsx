import { useState } from "react";
import { useRecordings, useTimeline, useRecordingStreamUrl } from "../hooks/useRecordings";
import { useCameras } from "../hooks/useCameras";
import { TimelinePlayer, RecordingPlayer } from "../components/recording";
import { Recording } from "../types/recording";
import { Film, Play, Trash2, X } from "lucide-react";

export default function Recordings() {
  const [selectedCameraId, setSelectedCameraId] = useState<string>("");
  const [selectedDate, setSelectedDate] = useState<string>(today());
  const [activePlaybackId, setActivePlaybackId] = useState<string | null>(null);
  const [activePlaybackTime, setActivePlaybackTime] = useState<string | null>(null);

  const { data: recordings } = useRecordings(
    selectedCameraId ? { camera_id: selectedCameraId } : undefined
  );
  const { data: cameras } = useCameras();
  const { data: segments = [] } = useTimeline(selectedCameraId, selectedDate);
  const streamUrl = useRecordingStreamUrl(activePlaybackId || "");

  const handleSeek = (time: string) => {
    setActivePlaybackTime(time);
  };

  const handlePlayRecording = (recording: Recording) => {
    setActivePlaybackId(recording.id);
    setActivePlaybackTime(null);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Recordings</h1>
        <div className="flex gap-2">
          <select
            value={selectedCameraId}
            onChange={(e) => setSelectedCameraId(e.target.value)}
            className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300"
          >
            <option value="">All Cameras</option>
            {(cameras || []).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300"
          />
        </div>
      </div>

      {selectedCameraId && (
        <div className="mb-4">
          <TimelinePlayer
            cameraId={selectedCameraId}
            date={selectedDate}
            segments={segments}
            onSeek={handleSeek}
            currentTime={activePlaybackTime}
          />
        </div>
      )}

      {activePlaybackId && (
        <div className="mb-4 relative">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-300">Now Playing</h3>
            <button
              onClick={() => { setActivePlaybackId(null); setActivePlaybackTime(null); }}
              className="p-1 bg-gray-800 hover:bg-gray-700 rounded text-gray-400"
            >
              <X size={16} />
            </button>
          </div>
          <RecordingPlayer src={streamUrl} className="max-h-96" />
        </div>
      )}

      {!recordings?.data?.length ? (
        <div className="bg-gray-900 rounded border border-gray-800 p-6 text-center text-gray-500">
          <Film size={32} className="mx-auto mb-2 text-gray-600" />
          No recordings found.
        </div>
      ) : (
        <div className="space-y-2">
          {recordings.data.map((rec: Recording) => (
            <div
              key={rec.id}
              className="flex items-center gap-4 p-3 bg-gray-900 rounded border border-gray-800 hover:border-gray-700"
            >
              <div className="w-24 h-14 bg-gray-800 rounded flex items-center justify-center shrink-0">
                <Film size={20} className="text-gray-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate">
                  {new Date(rec.start_time).toLocaleDateString()} {new Date(rec.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  {" – "}
                  {rec.end_time ? new Date(rec.end_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "ongoing"}
                </p>
                <p className="text-xs text-gray-500">
                  {(rec.duration_seconds / 60).toFixed(0)} min &middot; {(rec.file_size_bytes / 1024 / 1024).toFixed(1)} MB &middot; {rec.codec || "h264"}
                  {rec.has_audio && " &middot; audio"}
                </p>
              </div>
              <span className={`text-xs px-2 py-1 rounded ${
                rec.recording_type === "event" ? "bg-red-900 text-red-400" :
                rec.recording_type === "motion" ? "bg-yellow-900 text-yellow-400" :
                "bg-green-900 text-green-400"
              }`}>
                {rec.recording_type}
              </span>
              <div className="flex gap-1">
                <button
                  onClick={() => handlePlayRecording(rec)}
                  className="p-1.5 bg-blue-600 hover:bg-blue-700 rounded text-white"
                  title="Play"
                >
                  <Play size={14} />
                </button>
                <button className="p-1.5 bg-gray-800 hover:bg-red-600 rounded text-gray-400 hover:text-white" title="Delete">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function today(): string {
  return new Date().toISOString().split("T")[0];
}
