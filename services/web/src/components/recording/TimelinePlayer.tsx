import { useRef, useState, useEffect, useCallback } from "react";
import { TimelineSegment } from "../../types/recording";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface Props {
  segments: TimelineSegment[];
  cameraId: string;
  date: string;
  onSeek: (time: string) => void;
  currentTime?: string | null;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const SEGMENT_COLORS: Record<string, string> = {
  continuous: "bg-blue-600/70",
  motion: "bg-yellow-500/70",
  event: "bg-red-500/70",
};

function toMinutes(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

export default function TimelinePlayer({ segments, cameraId, date, onSeek, currentTime }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [hoveredTime, setHoveredTime] = useState<string | null>(null);

  const scroll = useCallback((dir: "left" | "right") => {
    if (scrollRef.current) {
      scrollRef.current.scrollBy({ left: dir === "left" ? -400 : 400, behavior: "smooth" });
    }
  }, []);

  useEffect(() => {
    const hour = new Date().getHours();
    setTimeout(() => {
      const el = document.getElementById(`tl-hour-${hour}`);
      el?.scrollIntoView({ inline: "center", behavior: "smooth" });
    }, 100);
  }, []);

  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left + (scrollRef.current?.scrollLeft || 0);
    const totalMinutes = (x / rect.width) * (24 * 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = Math.floor(totalMinutes % 60);
    const timeStr = `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:00`;
    onSeek(timeStr);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left + (scrollRef.current?.scrollLeft || 0);
    const totalMinutes = (x / rect.width) * (24 * 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = Math.floor(totalMinutes % 60);
    setHoveredTime(`${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}`);
  };

  const nowTotalMinutes = new Date().getHours() * 60 + new Date().getMinutes();
  const nowLinePos = `${(nowTotalMinutes / (24 * 60)) * 100}%`;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-300">Timeline — {date}</h3>
        <div className="flex gap-1">
          <button onClick={() => scroll("left")} className="p-1 bg-gray-800 hover:bg-gray-700 rounded text-gray-400">
            <ChevronLeft size={16} />
          </button>
          <button onClick={() => scroll("right")} className="p-1 bg-gray-800 hover:bg-gray-700 rounded text-gray-400">
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <div className="relative">
        <div
          ref={scrollRef}
          className="overflow-x-auto cursor-pointer rounded"
          style={{ height: 60 }}
          onClick={handleTimelineClick}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredTime(null)}
        >
          <div className="relative" style={{ width: `${24 * 80}px`, minWidth: "100%", height: 60 }}>
            {HOURS.map((h) => (
              <div
                key={h}
                id={`tl-hour-${h}`}
                className="absolute top-0 bottom-0 border-l border-gray-700"
                style={{ left: `${(h / 24) * 100}%` }}
              >
                <span className="absolute -top-1 left-0.5 text-xs text-gray-500 select-none">
                  {h}:00
                </span>
              </div>
            ))}

            {segments.map((seg, i) => {
              const start = toMinutes(seg.start_time);
              const end = seg.end_time ? toMinutes(seg.end_time) : start + 5;
              const left = (start / (24 * 60)) * 100;
              const width = Math.max(((end - start) / (24 * 60)) * 100, 0.5);
              const color = SEGMENT_COLORS[seg.recording_type] || SEGMENT_COLORS.continuous;
              return (
                <div
                  key={i}
                  className={`absolute top-5 h-5 ${color} rounded-sm hover:opacity-90`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  title={`${seg.recording_type}: ${seg.start_time}`}
                />
              );
            })}

            <div
              className="absolute top-0 bottom-0 w-0.5 bg-green-500 z-10"
              style={{ left: nowLinePos }}
            />
          </div>
        </div>

        {hoveredTime && (
          <div className="absolute -top-7 left-1/2 -translate-x-1/2 text-xs text-gray-400 bg-gray-800 px-2 py-0.5 rounded">
            {hoveredTime}
          </div>
        )}
      </div>

      <div className="flex gap-4 mt-2 text-xs text-gray-500">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-blue-600/70" />Continuous</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-yellow-500/70" />Motion</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-red-500/70" />Event</span>
      </div>
    </div>
  );
}
