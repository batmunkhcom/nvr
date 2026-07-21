export default function Cameras() {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Cameras</h1>
        <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm text-white">
          + Add Camera
        </button>
      </div>
      <div className="bg-gray-900 rounded border border-gray-800 p-6 text-center text-gray-500">
        No cameras configured. Click "Add Camera" to get started.
      </div>
    </div>
  );
}
