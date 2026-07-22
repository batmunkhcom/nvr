import { useEffect, useState, type FormEvent } from "react";
import { useWizardStore } from "../../store/wizardStore";
import { useStartDiscovery, useDiscoveryStatus, useDiscoveryResults } from "../../hooks/useDiscovery";
import { useCameras } from "../../hooks/useCameras";
import { Loader2, Wifi, CheckCircle, XCircle, Search } from "lucide-react";

function isValidTarget(s: string): boolean {
  const v = s.trim();
  if (!v) return false;
  // CIDR: 192.168.1.0/24
  if (/^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/.test(v)) return true;
  // Range: 192.168.1.100-192.168.1.150 or 192.168.1.100-150
  if (/^\d{1,3}(\.\d{1,3}){3}-(\d{1,3}(\.\d{1,3}){3}|\d{1,3})$/.test(v)) return true;
  return false;
}

export default function WizardDiscovery() {
  const { scanId, setScanId, setDiscoveredCameras, goNext } = useWizardStore();
  const start = useStartDiscovery();
  const status = useDiscoveryStatus(scanId);
  const results = useDiscoveryResults(scanId || "");
  const { data: cameras } = useCameras();

  // Pre-fill with /24 subnet derived from an existing camera, if any
  const guess = cameras?.length
    ? `${cameras[0].ip_address.split(".").slice(0, 3).join(".")}.0/24`
    : "";
  const [target, setTarget] = useState(guess);
  const [inputError, setInputError] = useState("");

  useEffect(() => {
    if (!target && guess) setTarget(guess);
  }, [guess]);

  useEffect(() => {
    if (status.data?.status === "completed" && scanId) {
      results.refetch().then((r) => {
        if (r.data) {
          setDiscoveredCameras(r.data);
        }
      });
    }
  }, [status.data?.status]);

  const handleStart = (e: FormEvent) => {
    e.preventDefault();
    const parts = target.split(",").map((s) => s.trim()).filter(Boolean);
    if (!parts.length || !parts.every(isValidTarget)) {
      setInputError("Enter a CIDR (192.168.1.0/24) or range (192.168.1.100-150)");
      return;
    }
    setInputError("");
    start.mutate({ subnets: parts }, {
      onSuccess: (data) => setScanId(data.scan_id),
    });
  };

  const s = status.data;
  const isComplete = s?.status === "completed";
  const isRunning = s?.status === "running" || s?.status === "pending";
  const isFailed = s?.status === "failed";

  const phaseLabel = () => {
    if (!s?.phases) return "Preparing";
    const phases = Object.entries(s.phases).filter(([,v]) => v === "running");
    return phases.length > 0 ? phases[0][0] : "Complete";
  };

  if (!scanId) {
    return (
      <div className="max-w-xl mx-auto mt-12">
        <h2 className="text-2xl font-bold mb-2">Network Scan</h2>
        <p className="text-gray-400 mb-6">
          Choose which part of your network to scan for cameras.
        </p>

        <form onSubmit={handleStart} className="bg-gray-900 rounded-lg border border-gray-800 p-6">
          <label className="block text-sm text-gray-400 mb-2">
            Subnet or IP range
          </label>
          <input
            type="text"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="192.168.1.0/24 or 192.168.1.100-192.168.1.150"
            className="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none mb-2"
            autoFocus
          />
          <p className="text-xs text-gray-600 mb-4">
            Examples: <code className="text-gray-400">192.168.1.0/24</code>,{" "}
            <code className="text-gray-400">192.168.1.100-150</code>,{" "}
            <code className="text-gray-400">192.168.1.100-192.168.1.150</code>.
            Separate multiple with commas.
          </p>
          {inputError && (
            <p className="text-sm text-red-400 mb-3">{inputError}</p>
          )}
          <button
            type="submit"
            disabled={start.isPending}
            className="w-full px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg font-medium text-white flex items-center justify-center gap-2"
          >
            {start.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Search size={16} />
            )}
            Start Scan
          </button>
        </form>

        <button
          onClick={goNext}
          className="mt-4 w-full px-4 py-2 text-sm text-gray-500 hover:text-gray-300"
        >
          Skip — add cameras manually
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto mt-12">
      <h2 className="text-2xl font-bold mb-2">Network Scan</h2>
      <p className="text-gray-400 mb-6">
        Scanning <span className="text-gray-200 font-medium">{target}</span> for cameras...
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
          onClick={() => setScanId("")}
          className="mt-6 w-full px-4 py-2.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
        >
          &larr; Change Range &amp; Retry
        </button>
      )}
    </div>
  );
}
