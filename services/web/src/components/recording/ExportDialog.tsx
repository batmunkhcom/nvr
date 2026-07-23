import { useState } from "react";
import { Download, X, Loader2 } from "lucide-react";

interface Props {
  recordingId: string;
  recordingName: string;
  onClose: () => void;
}

export default function ExportDialog({ recordingId, recordingName, onClose }: Props) {
  const [format, setFormat] = useState("mp4");
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const token = localStorage.getItem("access_token");
      const url = `/api/v1/recordings/${recordingId}/stream?download=true`;
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error("Download failed");
      const blob = await resp.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${recordingName}.${format}`;
      a.click();
      URL.revokeObjectURL(a.href);
      onClose();
    } catch {
      // silently fail — browser will show download or error
    }
    setExporting(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-gray-900 rounded-lg border border-gray-700 w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold">Export Recording</h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-800 rounded text-gray-400">
            <X size={18} />
          </button>
        </div>

        <p className="text-sm text-gray-400 mb-4 truncate">{recordingName}</p>

        <div className="space-y-3 mb-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Format</label>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200"
              disabled={exporting}
            >
              <option value="mp4">MP4 (H.264)</option>
            </select>
          </div>
        </div>

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm text-gray-300"
          >
            Cancel
          </button>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm text-white"
          >
            {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            {exporting ? "Downloading..." : "Download"}
          </button>
        </div>
      </div>
    </div>
  );
}
