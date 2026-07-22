import { useState, type FormEvent } from "react";
import { useCameraMutations, useCameraProbe } from "../../hooks/useCameras";
import type { ProbeResult } from "../../types/camera";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CameraAddDialog({ open, onClose }: Props) {
  const { createCamera } = useCameraMutations();
  const probe = useCameraProbe();

  const [ip, setIp] = useState("");
  const [probeResult, setProbeResult] = useState<ProbeResult | null>(null);
  const [name, setName] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [streamMain, setStreamMain] = useState("");
  const [streamSub, setStreamSub] = useState("");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const handleDetect = async () => {
    if (!ip.trim()) return;
    setError("");
    try {
      const result = await probe.mutateAsync(ip.trim());
      setProbeResult(result);
      if (result.reachable) {
        if (!name) setName(result.manufacturer || `Camera ${ip.trim()}`);
        if (!streamMain) setStreamMain(result.stream_main_uri || "");
        if (result.manufacturer && !username) setUsername("admin");
      } else {
        setError("No camera detected at this IP address.");
      }
    } catch {
      setError("Probe failed. Check the IP address and try again.");
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !ip.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      await createCamera.mutateAsync({
        name: name.trim(),
        ip_address: ip.trim(),
        username: username || "admin",
        password: password || undefined,
        auth_type: "basic",
        stream_main_uri: streamMain || undefined,
        stream_sub_uri: streamSub || undefined,
        recording_mode: "continuous",
        stream_transport: "tcp",
        location: location || undefined,
        notes: notes || undefined,
      });
      onClose();
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to add camera";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const r = probeResult;
  const isDetected = r?.reachable;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Add Camera</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl leading-none"
          >
            &times;
          </button>
        </div>

        {error && (
          <div className="bg-red-900/40 border border-red-800 rounded px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="flex gap-2">
          <input
            type="text"
            placeholder="IP Address (e.g. 192.168.1.100)"
            value={ip}
            onChange={(e) => {
              setIp(e.target.value);
              setProbeResult(null);
              setError("");
            }}
            className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
          />
          <button
            type="button"
            onClick={handleDetect}
            disabled={!ip.trim() || probe.isPending}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm text-white whitespace-nowrap"
          >
            {probe.isPending ? "Scanning..." : "Detect"}
          </button>
        </div>

        {r && isDetected && (
          <div className="bg-gray-800 border border-gray-700 rounded p-3 space-y-1.5 text-xs">
            <h3 className="text-blue-400 font-medium text-sm mb-1">
              Device Detected
            </h3>
            <Row label="Manufacturer" value={r.manufacturer} />
            <Row label="Model" value={r.model} />
            <Row label="Stream URI" value={r.stream_main_uri} />
            <Row label="Open Ports" value={r.open_ports.join(", ")} />
            <div className="flex gap-3 mt-1.5">
              <Badge label="RTSP" on={r.has_rtsp} />
              <Badge label="HTTP" on={r.has_http} />
              <Badge label="PTZ" on={r.has_ptz} />
              <Badge label="Audio" on={r.has_audio} />
              <Badge label="ONVIF" on={r.has_onvif} />
            </div>
          </div>
        )}

        {(!r || !isDetected) && r && !r.reachable && (
          <div className="bg-yellow-900/30 border border-yellow-800 rounded px-3 py-2 text-sm text-yellow-300">
            No device found. You can still enter details manually below.
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <Field
            label="Name"
            value={name}
            onChange={setName}
            placeholder="Camera name"
            required
          />
          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Username"
              value={username}
              onChange={setUsername}
              placeholder="Camera username"
            />
            <Field
              label="Password"
              value={password}
              onChange={setPassword}
              placeholder="Camera password"
              type="password"
            />
          </div>
          <Field
            label="Main Stream URI"
            value={streamMain}
            onChange={setStreamMain}
            placeholder="rtsp://192.168.1.100:554/Streaming/Channels/101"
          />
          <Field
            label="Sub Stream URI"
            value={streamSub}
            onChange={setStreamSub}
            placeholder="rtsp://192.168.1.100:554/Streaming/Channels/102"
          />
          <Field
            label="Location"
            value={location}
            onChange={setLocation}
            placeholder="e.g. Front Gate"
          />
          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={submitting || !name.trim() || !ip.trim()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm text-white"
            >
              {submitting ? "Adding..." : "Add Camera"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-200"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  type?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="block text-xs text-gray-400 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-200">{value || "--"}</span>
    </div>
  );
}

function Badge({ label, on }: { label: string; on: boolean }) {
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-xs font-medium ${
        on
          ? "bg-green-900/50 text-green-400 border border-green-800"
          : "bg-gray-800 text-gray-600 border border-gray-700"
      }`}
    >
      {label}
    </span>
  );
}
