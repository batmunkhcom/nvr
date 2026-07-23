import { useStorageBackends } from "../../hooks/useRecordings";

interface Props {
  value: string;
  onChange: (id: string) => void;
}

export default function StorageBackendSelect({ value, onChange }: Props) {
  const { data: backends, isLoading } = useStorageBackends();

  return (
    <div>
      <label className="block text-xs text-gray-400 mb-1">Storage Backend</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={isLoading}
        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none disabled:opacity-50"
      >
        <option value="">— Default (auto-select) —</option>
        {(backends || []).map((b) => (
          <option key={b.id} value={b.id}>
            {b.name} ({b.backend_type})
          </option>
        ))}
      </select>
      {!isLoading && !backends?.length && (
        <p className="text-[11px] text-gray-600 mt-1">
          No backends yet — add them under Storage.
        </p>
      )}
    </div>
  );
}
