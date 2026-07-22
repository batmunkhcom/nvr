import { useLocations } from "../../hooks/useLocations";

interface Props {
  value: string; // location_id or "" for none
  onChange: (id: string) => void;
}

export default function LocationSelect({ value, onChange }: Props) {
  const { data: locations, isLoading } = useLocations();

  return (
    <div>
      <label className="block text-xs text-gray-400 mb-1">Location</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={isLoading}
        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none disabled:opacity-50"
      >
        <option value="">— No location —</option>
        {(locations || []).map((loc) => (
          <option key={loc.id} value={loc.id}>
            {loc.name}
          </option>
        ))}
      </select>
      {!isLoading && !locations?.length && (
        <p className="text-[11px] text-gray-600 mt-1">
          No locations yet — add them under Settings → Locations.
        </p>
      )}
    </div>
  );
}
