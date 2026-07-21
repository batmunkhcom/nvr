import { useEvents, useAcknowledgeEvent } from "../hooks/useEvents";
import { Check, AlertTriangle, Info, XCircle } from "lucide-react";

const severityIcons: Record<string, typeof AlertTriangle> = {
  critical: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const severityColors: Record<string, string> = {
  critical: "text-red-400",
  warning: "text-yellow-400",
  info: "text-blue-400",
};

export default function Events() {
  const { data: events, isLoading } = useEvents();
  const ack = useAcknowledgeEvent();

  if (isLoading) {
    return (
      <div>
        <h1 className="text-2xl font-bold mb-4">Events</h1>
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-gray-800 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!events?.length) {
    return (
      <div>
        <h1 className="text-2xl font-bold mb-4">Events</h1>
        <div className="bg-gray-900 rounded border border-gray-800 p-6 text-center text-gray-500">
          No events detected yet.
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Events</h1>
        <span className="text-sm text-gray-400">{events.length} events</span>
      </div>
      <div className="space-y-2">
        {events.map((event) => {
          const Icon = severityIcons[event.severity] || Info;
          const color = severityColors[event.severity] || "text-gray-400";
          return (
            <div
              key={event.id}
              className={`flex items-center gap-3 p-3 rounded border ${
                event.is_acknowledged ? "bg-gray-900 border-gray-800" : "bg-gray-800 border-gray-700"
              }`}
            >
              <Icon className={color} size={18} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{event.event_type.replace(/_/g, " ")}</p>
                <p className="text-xs text-gray-500">
                  {new Date(event.created_at).toLocaleString()} &middot; {event.severity}
                </p>
              </div>
              {!event.is_acknowledged && (
                <button
                  onClick={() => ack.mutate(event.id)}
                  className="flex items-center gap-1 px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 rounded text-white"
                >
                  <Check size={12} /> Ack
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
