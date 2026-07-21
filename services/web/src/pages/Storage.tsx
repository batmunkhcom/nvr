export default function Storage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Storage</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-gray-900 rounded border border-gray-800 p-4">
          <p className="text-sm text-gray-400">Total</p>
          <p className="text-xl font-bold">— GB</p>
        </div>
        <div className="bg-gray-900 rounded border border-gray-800 p-4">
          <p className="text-sm text-gray-400">Used</p>
          <p className="text-xl font-bold">— GB</p>
        </div>
        <div className="bg-gray-900 rounded border border-gray-800 p-4">
          <p className="text-sm text-gray-400">Free</p>
          <p className="text-xl font-bold">— GB</p>
        </div>
      </div>
      <div className="bg-gray-900 rounded border border-gray-800 p-6 text-center text-gray-500">
        No storage backends configured.
      </div>
    </div>
  );
}
