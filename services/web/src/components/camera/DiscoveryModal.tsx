import { useEffect, useState } from "react";
import { useWizardStore } from "../../store/wizardStore";
import { useDiscovery, useDiscoveryStatus, useDiscoveryResults } from "../../hooks/useCameras";
import { useCameraMutations } from "../../hooks/useCameras";
import { Loader2, Wifi, CheckCircle, XCircle } from "lucide-react";
import type { DiscoveredDevice } from "../../types/camera";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function DiscoveryModal({ open, onClose }: Props) {
  const [scanId, setScanId] = useState<string | null>(null);
  const [results, setResults] = useState<DiscoveredDevice[]>([]);
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState<Set<string>>(new Set());
  const startScan = useDiscovery();
  const status = useDiscoveryStatus(scanId);
  const resultsQuery = useDiscoveryResults(scanId || "");
  const { createCamera } = useCameraMutations();

  useEffect(() => {
    if (open && !scanId) {
      startScan.mutate(
        { subnets: ["10.10.0.0/24"], timeout: 30 },
        { onSuccess: (data) => setScanId(data.scan_id) }
      );
    }
  }, [open]);

  useEffect(() => {
    if (status.data?.status === "completed" && scanId) {
      resultsQuery.refetch().then((r) => {
        if (r.data) setResults(r.data);
      });
    }
  }, [status.data?.status]);

  const handleAdd = async (dev: DiscoveredDevice) => {
    if (added.has(dev.ip_address)) return;
    setAdding(true);
    try {
      await createCamera.mutateAsync({
        name: dev.manufacturer ? `${dev.manufacturer} ${dev.ip_address}` : `Camera ${dev.ip_address}`,
        ip_address: dev.ip_address,
        username: "admin",
        password: "",
        auth_type: "basic",
        stream_main_uri: dev.stream_main_uri || `rtsp://${dev.ip_address}:554/Streaming/Channels/101`,
        recording_mode: "continuous",
        stream_transport: "tcp",
      });
      setAdded((s) => new Set(s).add(dev.ip_address));
    } catch {} finally { setAdding(false); }
  };

  if (!open) return null;
  const s = status.data;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-lg max-h-[80vh] overflow-y-auto p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Network Scan</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">&times;</button>
        </div>

        {s?.status === "running" && (
          <div className="flex items-center gap-3 text-blue-400">
            <Loader2 size={20} className="animate-spin" />
            <div>
              <p className="text-sm">Scanning... {s.scanned_ips}/{s.total_ips} IPs</p>
              <div className="w-full bg-gray-800 rounded-full h-1.5 mt-1">
                <div className="bg-blue-500 h-1.5 rounded-full transition-all" style={{ width: `${s.progress_pct}%` }} />
              </div>
            </div>
          </div>
        )}

        {s?.status === "completed" && (
          <p className="text-green-400 flex items-center gap-2"><CheckCircle size={16} /> Found {results.length} devices</p>
        )}

        {results.length > 0 && (
          <div className="space-y-1.5 max-h-64 overflow-y-auto">
            {results.map((dev) => (
              <div key={dev.ip_address} className="flex items-center gap-3 bg-gray-800 rounded p-2 text-sm">
                <Wifi size={14} className="text-gray-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-gray-200 truncate">{dev.ip_address}</p>
                  <p className="text-xs text-gray-500">
                    {dev.manufacturer || "Unknown"} &middot; ports: {dev.open_ports.join(",")} &middot; {dev.confidence}%
                  </p>
                </div>
                <button
                  onClick={() => handleAdd(dev)}
                  disabled={added.has(dev.ip_address) || adding}
                  className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-white"
                >
                  {added.has(dev.ip_address) ? "Added" : "Add"}
                </button>
              </div>
            ))}
          </div>
        )}

        {s?.status === "completed" && results.length === 0 && (
          <div className="text-center text-gray-500 py-4">
            <Wifi size={32} className="mx-auto mb-2" />
            <p>No cameras found on the network.</p>
          </div>
        )}

        <button onClick={onClose} className="w-full py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white">
          Close
        </button>
      </div>
    </div>
  );
}
