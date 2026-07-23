import { useState, type FormEvent } from "react";
import { Plus, Pencil, Trash2, MapPin } from "lucide-react";
import { useLocations, useLocationMutations } from "../../hooks/useLocations";
import type { Location } from "../../types/camera";
import { useConfirm } from "../ui/ConfirmDialog";
import EmptyState from "../ui/EmptyState";

export default function LocationsSection() {
  const { confirm } = useConfirm();
  const { data: locations, isLoading } = useLocations();
  const { createLocation, updateLocation, deleteLocation } = useLocationMutations();
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setSaving(true);
    setError("");
    try {
      await createLocation.mutateAsync({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
      });
      setNewName("");
      setNewDesc("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add location");
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (id: string, name: string, desc: string | null) => {
    setEditId(id);
    setEditName(name);
    setEditDesc(desc || "");
    setError("");
  };

  const handleSaveEdit = async () => {
    if (!editId || !editName.trim()) return;
    setSaving(true);
    setError("");
    try {
      await updateLocation.mutateAsync({
        id: editId,
        name: editName.trim(),
        description: editDesc.trim() || undefined,
      });
      setEditId(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    const ok = await confirm(`Delete location "${name}"? Cameras using it will keep working.`);
    if (!ok) return;
    try {
      await deleteLocation.mutateAsync(id);
    } catch { /* error handled by hook */ }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold mb-3">Locations</h2>

      <form onSubmit={handleAdd} className="flex gap-2 mb-4">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Location name (e.g. Front Gate)"
          required
          className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
        />
        <input
          type="text"
          value={newDesc}
          onChange={(e) => setNewDesc(e.target.value)}
          placeholder="Description (optional)"
          className="w-48 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
        />
        <button
          type="submit"
          disabled={saving || !newName.trim()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm text-white flex items-center gap-1"
        >
          <Plus size={14} /> Add
        </button>
      </form>

      {error && (
        <div className="bg-red-900/40 border border-red-800 rounded px-3 py-2 text-sm text-red-300 mb-3">
          {error}
        </div>
      )}

      {isLoading && (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-12 bg-gray-800 rounded animate-pulse" />
          ))}
        </div>
      )}

      {!isLoading && !locations?.length && (
        <EmptyState
          icon={<MapPin size={24} />}
          title="No locations yet"
          description="Add a location above to organize your cameras."
        />
      )}

      <div className="space-y-1.5">
        {locations?.map((loc: Location) =>
          editId === loc.id ? (
            <div key={loc.id} className="flex items-center gap-2 bg-gray-800 rounded px-3 py-2 border border-blue-700">
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="flex-1 px-2 py-1 bg-gray-900 border border-gray-600 rounded text-sm text-white outline-none"
                autoFocus
              />
              <input
                type="text"
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
                placeholder="Description"
                className="w-40 px-2 py-1 bg-gray-900 border border-gray-600 rounded text-sm text-gray-300 outline-none"
              />
              <button
                onClick={handleSaveEdit}
                disabled={saving || !editName.trim()}
                className="px-2 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs text-white"
              >
                Save
              </button>
              <button
                onClick={() => setEditId(null)}
                className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300"
              >
                Cancel
              </button>
            </div>
          ) : (
            <div
              key={loc.id}
              className="flex items-center justify-between bg-gray-900 border border-gray-800 hover:border-gray-700 rounded px-3 py-2"
            >
              <div className="flex items-center gap-3">
                <span className="text-sm text-white font-medium">{loc.name}</span>
                {loc.description && (
                  <span className="text-xs text-gray-500">{loc.description}</span>
                )}
                <span className="text-xs bg-gray-800 px-1.5 py-0.5 rounded text-gray-400">
                  {loc.camera_count} camera{loc.camera_count !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => startEdit(loc.id, loc.name, loc.description)}
                  title="Edit"
                  className="p-1 text-gray-500 hover:text-blue-400 rounded"
                >
                  <Pencil size={14} />
                </button>
                <button
                  onClick={() => handleDelete(loc.id, loc.name)}
                  title="Delete"
                  className="p-1 text-gray-500 hover:text-red-400 rounded"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ),
        )}
      </div>
    </div>
  );
}
