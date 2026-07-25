import { useState } from "react";
import { useActiveAlerts, useAcknowledgeAlert } from "../../hooks/useNetwork";
import type { NetworkAlert } from "../../types/network";
import { AlertTriangle, BellOff, Clock, ChevronLeft, ChevronRight } from "lucide-react";

export default function NetworkAlertPanel() {
  const [page, setPage] = useState(1);
  const { data: alerts } = useActiveAlerts(page);
  const acknowledge = useAcknowledgeAlert();

  if (!alerts || !alerts.data || alerts.data.length === 0) return null;

  const alertList = alerts.data as NetworkAlert[];
  const totalPages = Math.ceil(alerts.total_count / alerts.per_page);

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
        Active Alerts ({alerts.total_count})
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
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-3 pt-3 border-t border-gray-800">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 px-2 py-1 rounded disabled:opacity-30"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="text-xs text-gray-500">
            Page {alerts.page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 px-2 py-1 rounded disabled:opacity-30"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
