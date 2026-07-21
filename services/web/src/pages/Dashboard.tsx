export default function Dashboard() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
      <div className="grid grid-cols-2 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="aspect-video bg-gray-800 rounded border border-gray-700 flex items-center justify-center text-gray-500">
            Camera {i} — No stream
          </div>
        ))}
      </div>
    </div>
  );
}
