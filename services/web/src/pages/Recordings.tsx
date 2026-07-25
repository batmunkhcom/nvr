import { useMemo, useState, useCallback } from "react";
import { useRecordings, useTimeline, useRecordingStreamUrl, useDeleteRecording, useBulkDeleteRecordings, recordingThumbnailUrl } from "../hooks/useRecordings";
import { useCameras } from "../hooks/useCameras";
import { TimelinePlayer, RecordingPlayer } from "../components/recording";
import RecordingSchedulesSection from "../components/config/RecordingSchedulesSection";
import { Recording } from "../types/recording";
import { Film, Play, Trash2, X, ChevronLeft, ChevronRight, Clock, CalendarClock, Download } from "lucide-react";
import EmptyState from "../components/ui/EmptyState";
import { useToast } from "../components/ui/Toast";
import { useConfirm } from "../components/ui/ConfirmDialog";

function fmtBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
  return `${val.toFixed(val < 10 ? 1 : 0)} ${units[i]}`;
}

export default function Recordings() {
  const [activeTab, setActiveTab] = useState<"recordings" | "schedules">("recordings");
  const { confirm } = useConfirm();
  const [selectedCameraId, setSelectedCameraId] = useState<string>("");
  const [selectedDate, setSelectedDate] = useState<string>(today());
  const [fromTime, setFromTime] = useState<string>("");
  const [toTime, setToTime] = useState<string>("");
  const [activePlaybackId, setActivePlaybackId] = useState<string | null>(null);
  const [seekOffset, setSeekOffset] = useState<number | undefined>(undefined);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [olderThan, setOlderThan] = useState<string>("");
  const [page, setPage] = useState(1);
  const { toast } = useToast();

  const filters: Record<string, string> = { page: String(page), per_page: "25" };
  if (selectedCameraId) filters.camera_id = selectedCameraId;
  if (fromTime) filters.from_time = new Date(fromTime).toISOString();
  if (toTime) filters.to_time = new Date(toTime).toISOString();

  const { data: recordings } = useRecordings(filters);
  const { data: cameras } = useCameras();
  const { data: segments = [] } = useTimeline(selectedCameraId, selectedDate);
  const streamUrl = useRecordingStreamUrl(activePlaybackId || "");
  const deleteRecording = useDeleteRecording();
  const bulkDelete = useBulkDeleteRecordings();

  const recList = useMemo(() => recordings?.data || [], [recordings]);
  const allSelected = recList.length > 0 && recList.every((r) => selected.has(r.id));

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(recList.map((r) => r.id)));
    }
  };

  const toggleOne = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  /** Click on timeline: play the segment covering that moment, seeked. */
  const handleSeek = (time: string) => {
    const target = new Date(`${selectedDate}T${time}`);
    if (Number.isNaN(target.getTime())) return;
    const seg = segments.find((s) => {
      const start = new Date(s.start_time);
      const end = s.end_time ? new Date(s.end_time) : new Date(start.getTime() + 5 * 60_000);
      return target >= start && target <= end;
    });
    if (seg) {
      setActivePlaybackId(seg.id);
      setSeekOffset(Math.max(0, (target.getTime() - new Date(seg.start_time).getTime()) / 1000));
    } else {
      toast("warning", "No recording at that time");
    }
  };

  const handlePlayRecording = (recording: Recording) => {
    setActivePlaybackId(recording.id);
    setSeekOffset(undefined);
  };

  const handleDownload = useCallback(async (rec: Recording) => {
    try {
      const resp = await fetch(downloadUrl(rec.id));
      if (!resp.ok) throw new Error("Download failed");
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const fn = rec.camera_name
        ? `${rec.camera_name}_${(rec.start_time || "").replace(/[:+T]/g, "_").slice(0, 19)}.mp4`
        : `recording_${rec.id.slice(0, 8)}.mp4`;
      const a = document.createElement("a");
      a.href = url; a.download = fn;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      toast("error", "Download failed");
    }
  }, []);

  const activeRecording = useMemo(() => recList.find((r) => r.id === activePlaybackId), [recList, activePlaybackId]);

  const handleDelete = async (id: string) => {
    const ok = await confirm("Delete this recording?");
    if (!ok) return;
    try {
      await deleteRecording.mutateAsync(id);
      setSelected((prev) => { const n = new Set(prev); n.delete(id); return n; });
      toast("success", "Recording deleted");
    } catch {
      toast("error", "Failed to delete recording");
    }
  };

  const handleBulkDelete = async (mode: "selected" | "all" | "older") => {
    let payload: Parameters<typeof bulkDelete.mutateAsync>[0];
    let question: string;
    if (mode === "selected") {
      if (selected.size === 0) return;
      question = `Delete ${selected.size} selected recording(s)? This cannot be undone.`;
      payload = { ids: [...selected] };
    } else if (mode === "all") {
      question = selectedCameraId
        ? "Delete ALL recordings of this camera? This cannot be undone."
        : "Delete ALL recordings of ALL cameras? This cannot be undone.";
      payload = { delete_all: true, camera_id: selectedCameraId || undefined };
    } else {
      if (!olderThan) { toast("warning", "Pick a date first"); return; }
      question = `Delete every recording before ${olderThan}? This cannot be undone.`;
      payload = { before: new Date(olderThan).toISOString(), camera_id: selectedCameraId || undefined };
    }
    const ok = await confirm(question);
    if (!ok) return;
    try {
      const res = await bulkDelete.mutateAsync(payload);
      setSelected(new Set());
      toast("success", `Deleted ${res.deleted} recordings (${fmtBytes(res.freed_bytes)} freed)`);
    } catch {
      toast("error", "Bulk delete failed");
    }
  };

  const handleCameraChange = (id: string) => {
    setSelectedCameraId(id);
    setPage(1);
    setSelected(new Set());
  };

  const meta = recordings?.metadata;
  const totalPages = meta ? Math.ceil(meta.total / meta.per_page) : 1;

  return (
    <div className="page-enter">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold">Recordings</h1>
          <div className="flex gap-2 items-center">
            {activeTab === "recordings" && (
              <>
                <select
                 value={selectedCameraId}
                 onChange={(e) => handleCameraChange(e.target.value)}
                 className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300"
                 title="Filter by camera"
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
                 title="Timeline date"
                />
                <input
                 type="datetime-local"
                 value={fromTime}
                 onChange={(e) => { setFromTime(e.target.value); setPage(1); }}
                 className="px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-xs text-gray-300"
                 title="From (start of time range)"
                />
                <span className="text-gray-600 text-xs">–</span>
                <input
                 type="datetime-local"
                 value={toTime}
                 onChange={(e) => { setToTime(e.target.value); setPage(1); }}
                 className="px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-xs text-gray-300"
                 title="To (end of time range)"
                />
                {(fromTime || toTime) && (
                  <button
                    onClick={() => { setFromTime(""); setToTime(""); }}
                    className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded text-gray-400"
                    title="Clear time filter"
                  >
                    <X size={14} />
                  </button>
                )}
              </>
            )}
          </div>
        </div>

        <div className="flex gap-2 mb-4">
          <button
           onClick={() => setActiveTab("recordings")}
           className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
             activeTab === "recordings" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
           }`}
          >
            <Film size={14} /> Recordings
          </button>
          <button
           onClick={() => setActiveTab("schedules")}
           className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
             activeTab === "schedules" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
           }`}
          >
            <Clock size={14} /> Schedules
          </button>
        </div>

        {activeTab === "schedules" ? (
          <RecordingSchedulesSection />
        ) : (
          <>
            {selectedCameraId && (
              <div className="mb-4">
                <TimelinePlayer
                  cameraId={selectedCameraId}
                  date={selectedDate}
                  segments={segments}
                  onSeek={handleSeek}
                />
                <p className="text-[11px] text-gray-500 mt-1">
                  Click anywhere on the timeline to play the recording from that moment.
                </p>
              </div>
            )}

            {activePlaybackId && (
              <div className="mb-4 relative">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-gray-300">
                    Now Playing {seekOffset !== undefined && `(from ${Math.floor(seekOffset / 60)}:${String(Math.floor(seekOffset % 60)).padStart(2, "0")})`}
                  </h3>
                  <button
                    onClick={() => { setActivePlaybackId(null); setSeekOffset(undefined); }}
                    className="p-1 bg-gray-800 hover:bg-gray-700 rounded text-gray-400"
                  >
                    <X size={16} />
                  </button>
                </div>
                <RecordingPlayer
                  key={activePlaybackId}
                  src={streamUrl}
                  startOffset={seekOffset}
                  className="max-h-96"
                  filename={activeRecording
                    ? `${activeRecording.camera_name || "recording"}_${(activeRecording.start_time || "").replace(/[:+T]/g, "_").slice(0, 19)}.mp4`
                    : undefined}
                  onDownload={activeRecording ? () => handleDownload(activeRecording) : undefined}
                />
              </div>
            )}

            {/* Bulk actions */}
            <div className="flex items-center gap-2 mb-3 flex-wrap">
              <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="rounded border-gray-600 bg-gray-800 text-blue-600"
                />
                Select all
              </label>
              <button
                onClick={() => handleBulkDelete("selected")}
                disabled={selected.size === 0 || bulkDelete.isPending}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-red-700/80 hover:bg-red-600 disabled:opacity-40 rounded text-xs text-white"
              >
                <Trash2 size={12} /> Delete selected{selected.size > 0 && ` (${selected.size})`}
              </button>
              <button
                onClick={() => handleBulkDelete("all")}
                disabled={bulkDelete.isPending || recList.length === 0}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-gray-800 hover:bg-red-700 disabled:opacity-40 rounded text-xs text-gray-300 hover:text-white"
              >
                <Trash2 size={12} /> Delete all{selectedCameraId ? " (this camera)" : ""}
              </button>
              <div className="flex items-center gap-1.5 ml-auto">
                <CalendarClock size={14} className="text-gray-500" />
                <input
                  type="date"
                  value={olderThan}
                  onChange={(e) => setOlderThan(e.target.value)}
                  className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-gray-300"
                  title="Delete recordings before this date"
                />
                <button
                  onClick={() => handleBulkDelete("older")}
                  disabled={!olderThan || bulkDelete.isPending}
                  className="px-2.5 py-1.5 bg-gray-800 hover:bg-red-700 disabled:opacity-40 rounded text-xs text-gray-300 hover:text-white"
                >
                  Delete older
                </button>
              </div>
            </div>

            {!recList.length ? (
              <EmptyState
                icon={<Film size={28} />}
                title="No recordings found"
                description="Recordings appear here once the recording engine writes segments. Adjust the camera or time filter."
              />
            ) : (
              <>
                <div className="space-y-2">
                  {recList.map((rec: Recording) => (
                    <div
                      key={rec.id}
                      className={`flex items-center gap-4 p-3 bg-gray-900 rounded border transition-colors ${
                        selected.has(rec.id) ? "border-blue-600/60 bg-blue-900/10" : "border-gray-800 hover:border-gray-700"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(rec.id)}
                        onChange={() => toggleOne(rec.id)}
                        className="rounded border-gray-600 bg-gray-800 text-blue-600 flex-shrink-0"
                      />
                      <RecordingThumb id={rec.id} />
                      {rec.camera_name && (
                        <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-300 flex-shrink-0 min-w-[60px] text-center truncate max-w-[120px]" title={rec.camera_name}>
                          {rec.camera_name}
                        </span>
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate">
                          {new Date(rec.start_time).toLocaleDateString()}{" "}
                          {new Date(rec.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          {" – "}
                          {rec.end_time
                            ? new Date(rec.end_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                            : "ongoing"}
                        </p>
                        <p className="text-xs text-gray-500">
                          {(rec.duration_seconds / 60).toFixed(0)} min &middot;{" "}
                          {(rec.file_size_bytes / 1024 / 1024).toFixed(1)} MB &middot;{" "}
                          {rec.codec || "h264"}
                          {rec.has_audio && " &middot; audio"}
                        </p>
                      </div>
                      <span
                        className={`text-xs px-2 py-1 rounded ${
                          rec.recording_type === "event"
                            ? "bg-red-900 text-red-400"
                            : rec.recording_type === "motion"
                              ? "bg-yellow-900 text-yellow-400"
                              : "bg-green-900 text-green-400"
                        }`}
                      >
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
                        <button
                          onClick={() => handleDownload(rec)}
                          className="p-1.5 bg-gray-800 hover:bg-indigo-600 rounded text-gray-400 hover:text-white"
                          title="Download"
                        >
                          <Download size={14} />
                        </button>
                        <button
                          onClick={() => handleDelete(rec.id)}
                          disabled={deleteRecording.isPending}
                          className="p-1.5 bg-gray-800 hover:bg-red-600 rounded text-gray-400 hover:text-white disabled:opacity-50"
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                {totalPages > 1 && (
                  <div className="flex items-center justify-center gap-3 mt-4 pt-3 border-t border-gray-800">
                    <button
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page <= 1}
                      className="p-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded text-gray-400"
                    >
                      <ChevronLeft size={16} />
                    </button>
                    <span className="text-sm text-gray-400">
                      Page {page} of {totalPages}
                    </span>
                    <button
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      disabled={page >= totalPages}
                      className="p-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded text-gray-400"
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    );
}

function today(): string {
  return new Date().toISOString().split("T")[0];
}

function downloadUrl(recordingId: string): string {
  const token = localStorage.getItem("access_token") || "";
  return `/api/v1/recordings/${recordingId}/stream?download=true&token=${encodeURIComponent(token)}`;
}

function RecordingThumb({ id }: { id: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="w-24 h-14 bg-gray-800 rounded overflow-hidden flex items-center justify-center shrink-0">
      {failed ? (
        <Film size={20} className="text-gray-600" />
      ) : (
        <img
          src={recordingThumbnailUrl(id)}
          alt=""
          loading="lazy"
          className="w-full h-full object-cover"
          onError={() => setFailed(true)}
        />
      )}
    </div>
  );
}
