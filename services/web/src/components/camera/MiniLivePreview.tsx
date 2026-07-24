import { useState } from "react";
import { useStreamPlayer, type StreamType } from "../../hooks/useStreamPlayer";
import { useVideoAudio } from "../../hooks/useVideoAudio";
import { Loader2, WifiOff, RefreshCw, Volume2, VolumeX } from "lucide-react";

interface Props {
  cameraId: string;
}

export default function MiniLivePreview({ cameraId }: Props) {
  const [streamType, setStreamType] = useState<StreamType>("sub");
  const { state, retrySec, attachVideo, startStream } = useStreamPlayer({ cameraId, streamType });
  const { muted, toggleMute, attachVideo: attachWithAudio } = useVideoAudio(attachVideo);

  return (
    <div className="absolute inset-0">
      <video
        ref={attachWithAudio}
        muted autoPlay playsInline
        className={`absolute inset-0 w-full h-full object-cover ${state === "playing" ? "opacity-80" : "opacity-0"}`}
      />

      {state === "connecting" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-gray-900/70">
          <Loader2 size={18} className="text-gray-400 animate-spin" />
          <span className="text-[10px] text-gray-400">Connecting...</span>
        </div>
      )}
      {state === "loading" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-gray-900/70">
          <Loader2 size={18} className="text-blue-400 animate-spin" />
          <span className="text-[10px] text-gray-400">Buffering...</span>
        </div>
      )}
      {state === "retrying" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-gray-900/80">
          <WifiOff size={14} className="text-yellow-500" />
          <span className="text-[10px] text-gray-400">Retry in {retrySec}s</span>
          <button onClick={(e) => { e.stopPropagation(); startStream(); }} className="text-[10px] text-blue-400 hover:text-blue-300 pointer-events-auto">
            <RefreshCw size={10} /> Retry Now
          </button>
        </div>
      )}

      {state === "playing" && (
        <div className="absolute bottom-1 right-1 z-20 flex gap-1 pointer-events-auto">
          <button
            onClick={(e) => { e.stopPropagation(); toggleMute(); }}
            className="text-[10px] px-1 py-0.5 rounded bg-black/50 text-gray-400 hover:text-white hover:bg-black/60"
            title={muted ? "Unmute" : "Mute"}
          >
            {muted ? <VolumeX size={12} /> : <Volume2 size={12} />}
          </button>
          <button onClick={(e) => { e.stopPropagation(); setStreamType("sub"); }}
            className={`text-[10px] px-1.5 py-0.5 rounded ${streamType === "sub" ? "bg-blue-600 text-white" : "bg-black/50 text-gray-500 hover:text-gray-300"}`}>
            SUB
          </button>
          <button onClick={(e) => { e.stopPropagation(); setStreamType("main"); }}
            className={`text-[10px] px-1.5 py-0.5 rounded ${streamType === "main" ? "bg-blue-600 text-white" : "bg-black/50 text-gray-500 hover:text-gray-300"}`}>
            MAIN
          </button>
        </div>
      )}
    </div>
  );
}
