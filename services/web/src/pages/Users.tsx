import { useState } from "react";
import { useUsers, useUserMutations } from "../hooks/useUsers";
import { UserPlus, Trash2, Shield, Save } from "lucide-react";
import { useToast } from "../components/ui/Toast";
import type { UserRecord } from "../types/user";

export default function Users() {
  const [page, setPage] = useState(1);
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({ username: "", password: "", role: "viewer" });
  const { toast } = useToast();

  const { data, isLoading } = useUsers(page);
  const { create, update, remove } = useUserMutations();
  const users = data?.data || [];
  const meta = data?.metadata;

  const openAdd = () => {
    setEditingId(null);
    setForm({ username: "", password: "", role: "viewer" });
    setShowDialog(true);
  };

  const openEdit = (u: UserRecord) => {
    setEditingId(u.id);
    setForm({ username: u.username, password: "", role: u.role });
    setShowDialog(true);
  };

  const handleSubmit = async () => {
    if (!form.username.trim()) return;
    try {
      if (editingId) {
        await update.mutateAsync({
          id: editingId,
          role: form.role,
        });
        toast("success", "User updated");
      } else {
        if (!form.password) {
          toast("error", "Password is required");
          return;
        }
        await create.mutateAsync({
          username: form.username.trim(),
          password: form.password,
          role: form.role,
        });
        toast("success", "User created");
      }
      setShowDialog(false);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Failed to save user";
      toast("error", msg);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this user?")) return;
    try {
      await remove.mutateAsync(id);
      toast("success", "User deleted");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Failed to delete user";
      toast("error", msg);
    }
  };

  const roleColors: Record<string, string> = {
    admin: "bg-red-900 text-red-400",
    operator: "bg-blue-900 text-blue-400",
    viewer: "bg-gray-700 text-gray-400",
  };

  return (
    <div className="page-enter">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Users</h1>
        <button
          onClick={openAdd}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white"
        >
          <UserPlus size={14} /> Add User
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 bg-gray-800 rounded animate-pulse" />
          ))}
        </div>
      ) : users.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-8">No users found.</p>
      ) : (
        <>
          <div className="space-y-1">
            {users.map((u) => (
              <div
                key={u.id}
                className="flex items-center justify-between p-3 bg-gray-900 rounded border border-gray-800"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center text-sm font-bold text-gray-300">
                    {u.username[0]?.toUpperCase()}
                  </div>
                  <div>
                    <p className="text-sm text-white">{u.username}</p>
                    <p className="text-xs text-gray-500">
                      {u.email || "—"} &middot;{" "}
                      {u.last_login_at
                        ? `Last login: ${new Date(u.last_login_at).toLocaleDateString()}`
                        : "Never logged in"}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${roleColors[u.role] || ""}`}>
                    {u.role}
                  </span>
                  {u.is_active ? (
                    <span className="text-[10px] text-green-500">Active</span>
                  ) : (
                    <span className="text-[10px] text-red-500">Inactive</span>
                  )}
                  <button
                    onClick={() => openEdit(u)}
                    className="p-1.5 rounded text-gray-500 hover:bg-gray-800 hover:text-white"
                    title="Edit role"
                  >
                    <Shield size={14} />
                  </button>
                  <button
                    onClick={() => handleDelete(u.id)}
                    disabled={remove.isPending}
                    className="p-1.5 rounded text-gray-500 hover:bg-red-900 hover:text-red-400 disabled:opacity-50"
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          {meta && meta.total > meta.per_page && (
            <div className="flex items-center justify-center gap-3 mt-4 pt-3 border-t border-gray-800">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded text-sm text-gray-400"
              >
                Previous
              </button>
              <span className="text-sm text-gray-400">
                Page {page} of {Math.ceil(meta.total / meta.per_page)}
              </span>
              <button
                onClick={() =>
                  setPage((p) => Math.min(Math.ceil(meta.total / meta.per_page), p + 1))
                }
                disabled={page >= Math.ceil(meta.total / meta.per_page)}
                className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded text-sm text-gray-400"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {showDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-sm p-6 mx-4">
            <h2 className="text-lg font-bold mb-4">
              {editingId ? "Edit User" : "Add User"}
            </h2>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Username</label>
                <input
                  value={form.username}
                  onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))}
                  disabled={!!editingId}
                  className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white disabled:opacity-50"
                />
              </div>
              {!editingId && (
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Password</label>
                  <input
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))}
                    className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                  />
                </div>
              )}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Role</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm((p) => ({ ...p, role: e.target.value }))}
                  className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white"
                >
                  <option value="admin">Admin</option>
                  <option value="operator">Operator</option>
                  <option value="viewer">Viewer</option>
                </select>
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
                disabled={!form.username.trim() || create.isPending || update.isPending}
                className="flex items-center gap-1 px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm text-white"
              >
                <Save size={14} />
                {create.isPending || update.isPending ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
