import { HardDrive } from "lucide-react";
import EmptyState from "../components/ui/EmptyState";

export default function Storage() {
  return (
    <div className="page-enter">
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
      <EmptyState
        icon={<HardDrive size={28} />}
        title="No storage backends configured"
        description="Add an S3-compatible backend or local storage path in Settings."
      />
    </div>
  );
}
