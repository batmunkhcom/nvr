import { useEffect, useMemo, useState } from "react";
import { useEvents, useAcknowledgeEvent } from "../hooks/useEvents";
import { useCameras } from "../hooks/useCameras";
import { NvrEvent } from "../types/event";
import { Check, AlertTriangle, Info, XCircle, Bell, Car, PersonStanding, Dog, Package, ChevronLeft, ChevronRight, X, Maximize2 } from "lucide-react";
import EmptyState from "../components/ui/EmptyState";

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

const objectIcons: Record<string, typeof Car> = {
  car: Car,
  truck: Car,
  bus: Car,
  motorcycle: Car,
  bicycle: Car,
  person: PersonStanding,
  dog: Dog,
  cat: Dog,
};

function eventSnapshotUrl(eventId: string): string {
  const token = localStorage.getItem("access_token") || "";
  return `/api/v1/events/${eventId}/snapshot?token=${encodeURIComponent(token)}`;
}

function detectedObjects(event: NvrEvent): string[] {
  const objects = event.metadata?.objects;
  if (!objects || typeof objects !== "object") return [];
  if (Array.isArray(objects)) {
    return objects.map((o: any) => o.class || o.class_name || "").filter(Boolean);
  }
  return Object.keys(objects);
}

export default function Events() {
  const [cameraFilter, setCameraFilter] = useState("");
  const [page, setPage] = useState(1);
  const [zoomedEvent, setZoomedEvent] = useState<NvrEvent | null>(null);
  const filters: Record<string, string> = { page: String(page) };
  if (cameraFilter) filters.camera_id = cameraFilter;

  const { data: eventsPage, isLoading } = useEvents(filters);
  const { data: cameras } = useCameras();
  const ack = useAcknowledgeEvent();

  const events = eventsPage?.data || [];
  const meta = eventsPage?.metadata;
  const totalPages = meta ? Math.ceil(meta.total / meta.per_page) : 1;

  const cameraNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const c of cameras || []) map[c.id] = c.name;
    return map;
  }, [cameras]);

  useEffect(() => {
    if (!zoomedEvent) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setZoomedEvent(null); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [zoomedEvent]);

  if (isLoading) {
    return (
      <div className="page-enter">
        <h1 className="text-2xl font-bold mb-4">Events</h1>
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-gray-800 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="page-enter">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Events</h1>
        <div className="flex items-center gap-2">
          <select
            value={cameraFilter}
            onChange={(e) => { setCameraFilter(e.target.value); setPage(1); }}
            className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300"
          >
            <option value="">All Cameras</option>
            {(cameras || []).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <span className="text-sm text-gray-400">{meta?.total || 0} events</span>
        </div>
      </div>

      {!events.length ? (
        <EmptyState
          icon={<Bell size={28} />}
          title="No events detected yet"
          description="AI-detected objects (cars, people) and motion events will appear here with snapshots."
        />
      ) : (
        <>
          <div className="space-y-2">
            {events.map((event) => {
              const Icon = severityIcons[event.severity] || Info;
              const color = severityColors[event.severity] || "text-gray-400";
              const objects = detectedObjects(event);
              return (
                <div
                  key={event.id}
                  className={`flex items-center gap-3 p-3 rounded border ${
                    event.is_acknowledged ? "bg-gray-900 border-gray-800" : "bg-gray-800 border-gray-700"
                  }`}
                >
                  {event.snapshot_path ? (
                    <div className="relative group cursor-pointer flex-shrink-0" onClick={() => setZoomedEvent(event)}>
                      <img
                        src={eventSnapshotUrl(event.id)}
                        alt="detection"
                        loading="lazy"
                        className="w-40 h-24 object-cover rounded bg-gray-900"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                      />
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 rounded transition-colors flex items-center justify-center">
                        <Maximize2 size={16} className="text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                    </div>
                  ) : (
                    <div className="w-40 h-24 rounded bg-gray-900 flex items-center justify-center flex-shrink-0">
                      <Icon className={color} size={24} />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium">{event.event_type.replace(/_/g, " ")}</p>
                      {objects.map((obj) => {
                        const ObjIcon = objectIcons[obj] || Package;
                        return (
                          <span
                            key={obj}
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-blue-900/50 text-blue-300 rounded text-[11px]"
                          >
                            <ObjIcon size={11} /> {obj}
                          </span>
                        );
                      })}
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {cameraNames[event.camera_id] || "Camera"} &middot;{" "}
                      {new Date(event.start_time || event.created_at).toLocaleString()} &middot; {event.severity}
                    </p>
                  </div>
                  {!event.is_acknowledged && (
                    <button
                      onClick={() => ack.mutate(event.id)}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 rounded text-white flex-shrink-0"
                    >
                      <Check size={12} /> Ack
                    </button>
                  )}
                </div>
              );
            })}
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

      {zoomedEvent && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
          onClick={() => setZoomedEvent(null)}
        >
          <button
            onClick={() => setZoomedEvent(null)}
            className="absolute top-4 right-4 p-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-400 z-10"
          >
            <X size={20} />
          </button>
          <img
            src={eventSnapshotUrl(zoomedEvent.id)}
            alt="detection full"
            className="max-w-[90vw] max-h-[90vh] object-contain rounded"
            onClick={(e) => e.stopPropagation()}
            onError={(e) => { setZoomedEvent(null); }}
          />
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-xs text-gray-500 bg-black/60 px-3 py-1 rounded">
            {zoomedEvent.event_type.replace(/_/g, " ")} &middot;{" "}
            {cameraNames[zoomedEvent.camera_id] || "Camera"} &middot;{" "}
            {new Date(zoomedEvent.start_time || zoomedEvent.created_at).toLocaleString()}
          </div>
        </div>
      )}
    </div>
  );
}
