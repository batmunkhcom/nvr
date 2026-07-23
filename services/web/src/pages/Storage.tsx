import { useState } from "react";
import { HardDrive, Plus, Trash2, Edit3, Server } from "lucide-react";
import { useStorageUsage, useStorageBackends, useStorageMutations } from "../hooks/useRecordings";
import { useToast } from "../components/ui/Toast";
import type { StorageBackend } from "../types/recording";

const BACKEND_TYPES: Record<string, string> = {
  local: "Local Disk",
  nfs: "Network (NFS)",
  smb: "Network (SMB/CIFS)",
  s3: "S3 Compatible",
};

function fmtBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(val < 10 ? 1 : 0)} ${units[i]}`;
}

interface BackendForm {
  name: string;
  backend_type: string;
  mount_point: string;
  total_gb: string;
  priority: string;
  s3_bucket: string;
  s3_endpoint: string;
  s3_region: string;
  s3_access_key: string;
  s3_secret_key: string;
}

const emptyForm: BackendForm = {
  name: "",
  backend_type: "local",
  mount_point: "",
  total_gb: "",
  priority: "10",
  s3_bucket: "",
  s3_endpoint: "",
  s3_region: "",
  s3_access_key: "",
  s3_secret_key: "",
};

export default function Storage() {
  const storage = useStorageUsage();
  const backends = useStorageBackends();
  const { create, update, remove } = useStorageMutations();
  const { toast } = useToast();

  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<BackendForm>(emptyForm);

  const usage = storage.data;
  const backendList = backends.data || [];
  const isLoading = storage.isLoading || backends.isLoading;

  const openAdd = () => {
    setEditingId(null);
    setForm(emptyForm);
    setShowDialog(true);
  };

  const openEdit = (b: StorageBackend) => {
    setEditingId(b.id);
    setForm({
      name: b.name,
      backend_type: b.backend_type,
      mount_point: b.mount_point || "",
      total_gb: b.total_bytes > 0 ? String(Math.round(b.total_bytes / 1_073_741_824)) : "",
      priority: String(b.priority),
      s3_bucket: (b.config as Record<string, string>)?.bucket || "",
      s3_endpoint: (b.config as Record<string, string>)?.endpoint || "",
      s3_region: (b.config as Record<string, string>)?.region || "",
      s3_access_key: (b.config as Record<string, string>)?.access_key || "",
      s3_secret_key: "",
    });
    setShowDialog(true);
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) return;
    const config: Record<string, unknown> = {};
    if (form.backend_type === "s3") {
      config.bucket = form.s3_bucket;
      config.endpoint = form.s3_endpoint;
      config.region = form.s3_region;
      config.access_key = form.s3_access_key;
      config.secret_key = form.s3_secret_key;
    }

    const totalBytes = parseFloat(form.total_gb) > 0
      ? Math.round(parseFloat(form.total_gb) * 1_073_741_824)
      : 0;

    try {
      if (editingId) {
        await update.mutateAsync({
          id: editingId,
          name: form.name.trim(),
          mount_point: form.mount_point || undefined,
          config: Object.keys(config).length > 0 ? config : undefined,
          total_bytes: totalBytes || undefined,
          priority: parseInt(form.priority) || 10,
        });
        toast("success", "Storage backend updated");
      } else {
        await create.mutateAsync({
          name: form.name.trim(),
          backend_type: form.backend_type,
          mount_point: form.mount_point || undefined,
          config: Object.keys(config).length > 0 ? config : undefined,
          total_bytes: totalBytes,
          priority: parseInt(form.priority) || 10,
        });
        toast("success", "Storage backend added");
      }
      setShowDialog(false);
    } catch {
      toast("error", "Failed to save storage backend");
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("Remove this storage backend?")) return;
    try {
      await remove.mutateAsync(id);
      toast("success", "Storage backend removed");
    } catch {
      toast("error", "Failed to remove storage backend");
    }
  };

  const isS3 = form.backend_type === "s3";

  return (
    <div className="page-enter">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Storage</h1>
        <button
          onClick={openAdd}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white"
        >
          <Plus size={14} /> Add Backend
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-gray-900 rounded border border-gray-800 p-4">
          <p className="text-sm text-gray-400">Total</p>
          <p className="text-xl font-bold mt-1">
            {usage ? fmtBytes(usage.total_bytes) : "—"}
          </p>
        </div>
        <div className="bg-gray-900 rounded border border-gray-800 p-4">
          <p className="text-sm text-gray-400">Used</p>
          <p className="text-xl font-bold mt-1">
            {usage ? fmtBytes(usage.used_bytes) : "—"}
          </p>
        </div>
        <div className="bg-gray-900 rounded border border-gray-800 p-4">
          <p className="text-sm text-gray-400">Free</p>
          <p className="text-xl font-bold mt-1">
            {usage ? fmtBytes(usage.free_bytes) : "—"}
          </p>
        </div>
        <div className="bg-gray-900 rounded border border-gray-800 p-4">
          <p className="text-sm text-gray-400">Usage</p>
          <div className="mt-1">
            <div className="w-full bg-gray-700 rounded h-2.5 mb-1.5">
              <div
                className="bg-blue-600 h-2.5 rounded"
                style={{ width: `${Math.min(usage?.total_bytes ? ((usage.used_bytes / usage.total_bytes) * 100) : 0, 100)}%` }}
              />
            </div>
            <p className="text-xs text-gray-500">
              {usage?.total_bytes
                ? `${Math.round((usage.used_bytes / usage.total_bytes) * 100)}%`
                : "—"}
            </p>
          </div>
        </div>
      </div>

      {/* Backend list */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-16 bg-gray-800 rounded animate-pulse" />
          ))}
        </div>
      ) : backendList.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <HardDrive size={32} className="mx-auto mb-3 opacity-50" />
          <p className="text-sm">No storage backends configured</p>
          <p className="text-xs mt-1 text-gray-600">
            Add an S3 bucket, local path, or network share to store recordings.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {backendList.map((b) => (
            <div
              key={b.id}
              className="bg-gray-900 rounded border border-gray-800 p-4 flex items-center justify-between"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className={`w-8 h-8 rounded flex items-center justify-center ${
                    b.health_status === "healthy"
                      ? "bg-green-900 text-green-400"
                      : b.health_status === "degraded"
                        ? "bg-yellow-900 text-yellow-400"
                        : "bg-gray-700 text-gray-400"
                  }`}
                >
                  <Server size={16} />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white truncate">
                      {b.name}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-400">
                      {BACKEND_TYPES[b.backend_type] || b.backend_type}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded ${
                        b.is_active
                          ? "bg-green-900 text-green-400"
                          : "bg-gray-700 text-gray-500"
                      }`}
                    >
                      {b.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {fmtBytes(b.available_bytes)} free / {fmtBytes(b.total_bytes)} total
                    {b.mount_point && (
                      <span className="ml-2 font-mono text-gray-600">
                        {b.mount_point}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1 ml-4">
                <button
                  onClick={() => openEdit(b)}
                  className="p-1.5 rounded text-gray-500 hover:bg-gray-800 hover:text-white"
                  title="Edit"
                >
                  <Edit3 size={14} />
                </button>
                <button
                  onClick={() => handleDelete(b.id)}
                  className="p-1.5 rounded text-gray-500 hover:bg-red-900 hover:text-red-400"
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add / Edit dialog */}
      {showDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-md p-6 mx-4 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-bold mb-4">
              {editingId ? "Edit Backend" : "Add Storage Backend"}
            </h2>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Main NAS"
                  className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1">Type</label>
                <select
                  value={form.backend_type}
                  onChange={(e) => setForm((p) => ({ ...p, backend_type: e.target.value }))}
                  className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                >
                  {Object.entries(BACKEND_TYPES).map(([val, label]) => (
                    <option key={val} value={val}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  Mount Path / URL
                </label>
                <input
                  value={form.mount_point}
                  onChange={(e) => setForm((p) => ({ ...p, mount_point: e.target.value }))}
                  placeholder={isS3 ? "https://s3.amazonaws.com" : "/data/recordings"}
                  className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                />
              </div>

              {isS3 && (
                <>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Bucket</label>
                    <input
                      value={form.s3_bucket}
                      onChange={(e) => setForm((p) => ({ ...p, s3_bucket: e.target.value }))}
                      className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Region</label>
                    <input
                      value={form.s3_region}
                      onChange={(e) => setForm((p) => ({ ...p, s3_region: e.target.value }))}
                      className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Access Key</label>
                    <input
                      value={form.s3_access_key}
                      onChange={(e) => setForm((p) => ({ ...p, s3_access_key: e.target.value }))}
                      className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Secret Key</label>
                    <input
                      type="password"
                      value={form.s3_secret_key}
                      onChange={(e) => setForm((p) => ({ ...p, s3_secret_key: e.target.value }))}
                      placeholder={editingId ? "•••••••• (unchanged if blank)" : ""}
                      className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                    />
                  </div>
                </>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">
                    Capacity (GB, 0 = auto)
                  </label>
                  <input
                    type="number"
                    value={form.total_gb}
                    onChange={(e) => setForm((p) => ({ ...p, total_gb: e.target.value }))}
                    min="0"
                    className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Priority</label>
                  <input
                    type="number"
                    value={form.priority}
                    onChange={(e) => setForm((p) => ({ ...p, priority: e.target.value }))}
                    min="1"
                    max="99"
                    className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowDialog(false)}
                className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-300"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={!form.name.trim() || create.isPending || update.isPending}
                className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm text-white"
              >
                {create.isPending || update.isPending ? "Saving..." : editingId ? "Update" : "Add"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
