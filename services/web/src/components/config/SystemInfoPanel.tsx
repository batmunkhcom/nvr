import { useQuery } from "@tanstack/react-query";
import apiClient from "../../api/client";

export default function SystemInfoPanel() {
  const { data: health } = useQuery({
    queryKey: ["system", "health"],
    queryFn: () => apiClient.get("/system/health").then((r) => r.data?.data),
    refetchInterval: 30_000,
  });

  return (
    <div>
      <h2 className="text-lg font-bold text-white mb-4">System Information</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <InfoTile label="Version" value={health?.version || "—"} />
        <InfoTile
          label="Uptime"
          value={`${Math.round((health?.uptime_seconds || 0) / 3600)} hours`}
        />
        <InfoTile label="Database" value={health?.checks?.database || "ok"} ok />
        <InfoTile label="Redis" value={health?.checks?.redis || "ok"} ok />
        <InfoTile
          label="Cameras Online"
          value={`${health?.cameras?.online || 0} / ${health?.cameras?.total || 0}`}
        />
        <InfoTile label="AI Engine" value="OpenAI / Ollama" dim />
        <InfoTile
          label="CPU Usage"
          value={health?.cpu_percent != null ? `${health.cpu_percent}%` : "—"}
        />
        <InfoTile
          label="Memory"
          value={health?.memory_mb != null ? `${health.memory_mb} MB` : "—"}
        />
        <InfoTile
          label="API Version"
          value={health?.api_version || "—"}
          dim
        />
      </div>
    </div>
  );
}

function InfoTile({
  label,
  value,
  ok,
  dim,
}: {
  label: string;
  value: string;
  ok?: boolean;
  dim?: boolean;
}) {
  return (
    <div className="bg-gray-800/70 rounded-lg border border-gray-700/50 p-3.5">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p
        className={`text-sm font-mono font-medium ${
          ok ? "text-green-400" : dim ? "text-blue-400/70" : "text-white"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
