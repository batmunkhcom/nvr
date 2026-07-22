import { useEffect, useState } from "react";
import { useWizardStore } from "../../store/wizardStore";
import { useStartDiscovery, useDiscoveryStatus, useDiscoveryResults } from "../../hooks/useDiscovery";
import { Loader2, Wifi, CheckCircle, XCircle } from "lucide-react";

export default function WizardDiscovery() {
  const { scanId, setScanId, setDiscoveredCameras, goNext } = useWizardStore();
  const start = useStartDiscovery();
  const status = useDiscoveryStatus(scanId);
  const results = useDiscoveryResults(scanId || "");
  const [started, setStarted] = useState(false);

  useEffect(() => {
    if (!started && !scanId) {
      setStarted(true);
      start.mutate({}, {
        onSuccess: (data) => setScanId(data.scan_id),
      });
    }
  }, [started, scanId]);

  useEffect(() => {
    if (status.data?.status === "completed" && scanId) {
      results.refetch().then((r) => {
        if (r.data) {
          setDiscoveredCameras(r.data);
        }
      });
    }
  }, [status.data?.status]);

  const s = status.data;
  const isComplete = s?.status === "completed";
  const isRunning = s?.status === "running" || s?.status === "pending";
  const isFailed = s?.status === "failed";

  const phaseLabel = () => {
    if (!s?.phases) return "Preparing";
    const phases = Object.entries(s.phases).filter(([,v]) => v === "running");
    return phases.length > 0 ? phases[0][0] : "Complete";
  };

  return (
    <div className="max-w-xl mx-auto mt-12">
      <h2 className="text-2xl font-bold mb-2">Network Scan</h2>
      <p className="text-gray-400 mb-6">
        Scanning your local network for ONVIF, RTSP, and IP cameras...
      </p>

      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <div className="flex items-center gap-4 mb-4">
          {isRunning ? (
            <Loader2 size={32} className="text-blue-400 animate-spin" />
          ) : isComplete ? (
            <CheckCircle size={32} className="text-green-400" />
          ) : isFailed ? (
            <XCircle size={32} className="text-red-400" />
          ) : (
            <Wifi size={32} className="text-gray-600" />
          )}
          <div>
            <p className="font-semibold">
              {isRunning ? "Scanning..." : isComplete ? "Scan Complete" : isFailed ? "Scan Failed" : "Initializing..."}
            </p>
            <p className="text-sm text-gray-500">
              {phaseLabel()} &middot; {s?.found_count || 0} cameras found
              {s ? ` (${s.scanned_ips}/${s.total_ips} IPs)` : ""}
            </p>
          </div>
        </div>

        <div className="w-full bg-gray-800 rounded-full h-2 mb-2">
          <div
            className="bg-blue-500 h-2 rounded-full transition-all duration-500"
            style={{ width: `${s?.progress_pct || 0}%` }}
          />
        </div>
        <p className="text-xs text-gray-500">{s?.progress_pct || 0}% complete</p>
      </div>

      {isComplete && (
        <button
          onClick={goNext}
          className="mt-6 w-full px-4 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium text-white"
        >
          Review Found Cameras &rarr;
        </button>
      )}

      {isFailed && (
        <button
          onClick={goNext}
          className="mt-6 w-full px-4 py-2.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
        >
          Skip — Add Manually &rarr;
        </button>
      )}
    </div>
  );
}
