import { useActiveAlerts, useAcknowledgeAlert } from "../../hooks/useNetwork";
import type { NetworkAlert } from "../../types/network";
import { AlertTriangle, BellOff, Clock } from "lucide-react";

export default function NetworkAlertPanel() {
  const { data: alerts } = useActiveAlerts();
  const acknowledge = useAcknowledgeAlert();

  const alertList = (alerts || []) as NetworkAlert[];

  if (alertList.length === 0) return null;

  const severityIcon = (severity: string) => {
    if (severity === "critical") return <AlertTriangle size={14} className="text-red-400" />;
    return <BellOff size={14} className="text-yellow-400" />;
  };

  const timeAgo = (dateStr: string) => {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}h ${mins % 60}m ago`;
  };

  return (
    <div className="bg-gray-900 rounded border border-gray-800 p-4 mb-6">
      <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
        <AlertTriangle size={16} className="text-orange-400" />
        Active Alerts ({alertList.length})
      </h3>
      <div className="space-y-2">
        {alertList.map((alert) => (
          <div key={alert.id} className="flex items-center justify-between bg-gray-800 rounded p-3 border border-gray-700">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              {severityIcon(alert.severity)}
              <div className="min-w-0">
                <div className="text-sm text-gray-200 truncate">{alert.camera_name}</div>
                <div className="text-xs text-gray-400 truncate">{alert.message}</div>
              </div>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0 ml-3">
              <span className="text-[10px] text-gray-500 flex items-center gap-1">
                <Clock size={10} />
                {timeAgo(alert.triggered_at)}
              </span>
              <button
                onClick={() => acknowledge.mutate(alert.id)}
                disabled={acknowledge.isPending}
                className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 px-2 py-1 rounded transition-colors disabled:opacity-50"
              >
                Acknowledge
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
