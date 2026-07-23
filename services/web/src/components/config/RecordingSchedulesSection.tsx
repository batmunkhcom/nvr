import { useState } from "react";
import { useRecordingSchedules, useRecordingScheduleMutations } from "../../hooks/useRecordingSchedules";
import { useCameras } from "../../hooks/useCameras";
import { useToast } from "../ui/Toast";
import { useConfirm } from "../ui/ConfirmDialog";
import EmptyState from "../ui/EmptyState";
import { Clock, Plus, Trash2, Save } from "lucide-react";
import type { RecordingSchedule } from "../../types/recording";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function RecordingSchedulesSection() {
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({
    camera_id: "",
    schedule_name: "",
    time_start: "00:00",
    time_end: "23:59",
    days: new Set<number>([1, 2, 3, 4, 5]),
  });

  const { data: schedules } = useRecordingSchedules();
  const { data: cameras } = useCameras();
  const { create, update, remove } = useRecordingScheduleMutations();
  const { toast } = useToast();
  const { confirm } = useConfirm();

  const openAdd = () => {
    setEditingId(null);
    setForm({ camera_id: "", schedule_name: "", time_start: "00:00", time_end: "23:59", days: new Set([1, 2, 3, 4, 5]) });
    setShowDialog(true);
  };

  const openEdit = (s: RecordingSchedule) => {
    setEditingId(s.id);
    setForm({
      camera_id: s.camera_id,
      schedule_name: s.schedule_name,
      time_start: s.time_start?.slice(0, 5) || "00:00",
      time_end: s.time_end?.slice(0, 5) || "23:59",
      days: new Set(s.days_of_week),
    });
    setShowDialog(true);
  };

  const toggleDay = (d: number) => {
    setForm((p) => {
      const next = new Set(p.days);
      if (next.has(d)) next.delete(d); else next.add(d);
      return { ...p, days: next };
    });
  };

  const handleSubmit = async () => {
    if (!form.schedule_name.trim() || !form.camera_id) return;
    const daysArr = Array.from(form.days).sort();
    try {
      if (editingId) {
        await update.mutateAsync({ id: editingId, days_of_week: daysArr, time_start: form.time_start, time_end: form.time_end });
        toast("success", "Schedule updated");
      } else {
        await create.mutateAsync({ camera_id: form.camera_id, schedule_name: form.schedule_name.trim(), days_of_week: daysArr, time_start: form.time_start, time_end: form.time_end });
        toast("success", "Schedule created");
      }
      setShowDialog(false);
    } catch (err: unknown) {
      toast("error", (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed");
    }
  };

  const handleDelete = async (id: string) => {
    const ok = await confirm("Delete this schedule?");
    if (!ok) return;
    try { await remove.mutateAsync(id); toast("success", "Deleted"); } catch { toast("error", "Failed"); }
  };

  const cameraMap = Object.fromEntries((cameras || []).map((c) => [c.id, c.name]));
  const list = schedules || [];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-gray-300">Recording Schedules</h2>
        <button onClick={openAdd} className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-xs text-white">
          <Plus size={12} /> Add
        </button>
      </div>

      {list.length === 0 ? (
        <EmptyState
          icon={<Clock size={24} />}
          title="No recording schedules"
          description="Add a schedule to control when cameras record."
        />
      ) : (
        <div className="space-y-1">
          {list.map((s) => (
            <div key={s.id} className="flex items-center justify-between p-3 bg-gray-800 rounded">
              <div className="flex items-center gap-3">
                <Clock size={15} className="text-gray-500" />
                <div>
                  <p className="text-sm text-white">{s.schedule_name}</p>
                  <p className="text-xs text-gray-500">
                    {cameraMap[s.camera_id] || s.camera_id} &middot; {s.time_start?.slice(0, 5)}–{s.time_end?.slice(0, 5)}
                    &middot; {s.days_of_week.map((d) => DAYS[d - 1]).join(",")}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${s.is_active ? "bg-green-900 text-green-400" : "bg-gray-700 text-gray-500"}`}>
                  {s.is_active ? "Active" : "Off"}
                </span>
                <button onClick={() => openEdit(s)} className="p-1.5 rounded text-gray-500 hover:bg-gray-700 hover:text-white" title="Edit"><Save size={12} /></button>
                <button onClick={() => handleDelete(s.id)} className="p-1.5 rounded text-gray-500 hover:bg-red-900 hover:text-red-400" title="Delete"><Trash2 size={12} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-sm p-6 mx-4">
            <h2 className="text-lg font-bold mb-4">{editingId ? "Edit" : "Add"} Schedule</h2>
            <div className="space-y-3">
              {!editingId && (
                <>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Camera</label>
                    <select value={form.camera_id} onChange={(e) => setForm((p) => ({ ...p, camera_id: e.target.value }))} className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white">
                      <option value="">— Select —</option>
                      {(cameras || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Name</label>
                    <input value={form.schedule_name} onChange={(e) => setForm((p) => ({ ...p, schedule_name: e.target.value }))} className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white" />
                  </div>
                </>
              )}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Start</label>
                  <input type="time" value={form.time_start} onChange={(e) => setForm((p) => ({ ...p, time_start: e.target.value }))} className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">End</label>
                  <input type="time" value={form.time_end} onChange={(e) => setForm((p) => ({ ...p, time_end: e.target.value }))} className="w-full px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm text-white" />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Days</label>
                <div className="flex gap-1 flex-wrap">
                  {DAYS.map((label, i) => {
                    const d = i + 1;
                    return (
                      <button key={d} onClick={() => toggleDay(d)} className={`px-2 py-1 rounded text-xs ${form.days.has(d) ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-500"}`}>
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowDialog(false)} className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm text-gray-300">Cancel</button>
              <button onClick={handleSubmit} disabled={create.isPending || update.isPending} className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm text-white">
                {create.isPending || update.isPending ? "..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
