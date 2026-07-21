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
  const [progress, setProgress] = useState(0);

  const handleExport = async () => {
    setExporting(true);
    setProgress(0);
    const interval = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) {
          clearInterval(interval);
          setExporting(false);
          return 100;
        }
        return p + 10;
      });
    }, 300);
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

        <p className="text-sm text-gray-400 mb-4">{recordingName}</p>

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
              <option value="mkv">MKV (Lossless)</option>
              <option value="avi">AVI</option>
            </select>
          </div>
        </div>

        {exporting && (
          <div className="mb-4">
            <div className="w-full bg-gray-800 rounded-full h-2">
              <div
                className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">{progress}% complete</p>
          </div>
        )}

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
            {exporting ? "Exporting..." : "Export"}
          </button>
        </div>
      </div>
    </div>
  );
}
