export default function Recordings() {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Recordings</h1>
        <div className="flex gap-2">
          <select className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300">
            <option>All Cameras</option>
          </select>
          <select className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300">
            <option>All Types</option>
            <option>Continuous</option>
            <option>Motion</option>
            <option>Event</option>
          </select>
        </div>
      </div>
      <div className="space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex items-center gap-4 p-3 bg-gray-900 rounded border border-gray-800">
            <div className="w-24 h-14 bg-gray-800 rounded flex items-center justify-center text-gray-600 text-xs">
              Preview
            </div>
            <div className="flex-1">
              <p className="text-sm">Recording #{i}</p>
              <p className="text-xs text-gray-500">Camera Front Door &middot; 15 min &middot; 2h ago</p>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-green-900 text-green-400">continuous</span>
          </div>
        ))}
      </div>
    </div>
  );
}
