import { useState } from "react";
import { useAuthStore } from "../store/authStore";
import { useProfile, useProfileMutations } from "../hooks/useProfile";
import { User, Shield, Mail, Save, Key, AlertCircle, Loader2, CheckCircle } from "lucide-react";
import { useToast } from "../components/ui/Toast";

export default function Profile() {
  const user = useAuthStore((s) => s.user);
  const { data: profile, isLoading } = useProfile();
  const { updateProfile, changePassword } = useProfileMutations();
  const { toast } = useToast();

  const [email, setEmail] = useState("");
  const [emailDirty, setEmailDirty] = useState(false);

  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [pwdConfirm, setPwdConfirm] = useState("");
  const [pwdError, setPwdError] = useState("");

  const initEmail = (val: string | null) => {
    if (!emailDirty) setEmail(val || "");
  };

  const handleSaveEmail = async () => {
    try {
      await updateProfile.mutateAsync({ email: email || null });
      setEmailDirty(false);
      toast("success", "Email updated");
    } catch {
      toast("error", "Failed to update email");
    }
  };

  const handleChangePassword = async () => {
    setPwdError("");
    if (newPwd.length < 6) { setPwdError("Password must be at least 6 characters"); return; }
    if (newPwd !== pwdConfirm) { setPwdError("Passwords do not match"); return; }
    try {
      await changePassword.mutateAsync({ old_password: oldPwd, new_password: newPwd });
      setOldPwd(""); setNewPwd(""); setPwdConfirm("");
      toast("success", "Password changed successfully");
    } catch (e: any) {
      const msg = e?.response?.data?.detail || "Failed to change password";
      setPwdError(msg);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={24} className="text-gray-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="page-enter max-w-lg mx-auto">
      <h1 className="text-2xl font-bold mb-6">Profile</h1>

      <div className="bg-gray-900 border border-gray-800 rounded p-6 mb-6">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-12 h-12 rounded-full bg-blue-900/50 flex items-center justify-center">
            <User size={22} className="text-blue-400" />
          </div>
          <div>
            <p className="text-lg font-medium text-gray-200">{user?.username}</p>
            <p className="text-xs text-gray-500 flex items-center gap-1">
              <Shield size={11} />
              {profile?.role ?? user?.role ?? "user"}
            </p>
          </div>
        </div>

        <div className="space-y-3 text-sm">
          <div className="flex justify-between text-gray-400">
            <span>Role</span>
            <span className="text-gray-300 capitalize">{profile?.role ?? "-"}</span>
          </div>
          <div className="flex justify-between text-gray-400">
            <span>Status</span>
            <span className={profile?.is_active ? "text-green-400" : "text-red-400"}>
              {profile?.is_active ? "Active" : "Disabled"}
            </span>
          </div>
          {profile?.last_login_at && (
            <div className="flex justify-between text-gray-400">
              <span>Last login</span>
              <span className="text-gray-300">{new Date(profile.last_login_at).toLocaleString()}</span>
            </div>
          )}
          {profile?.created_at && (
            <div className="flex justify-between text-gray-400">
              <span>Created</span>
              <span className="text-gray-300">{new Date(profile.created_at).toLocaleDateString()}</span>
            </div>
          )}
        </div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Mail size={16} className="text-gray-400" />
          Email
        </h2>
        <div className="flex gap-2">
          <input
            type="email"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setEmailDirty(true); }}
            onFocus={() => { if (!emailDirty && profile?.email) initEmail(profile.email); }}
            placeholder="your@email.com"
            className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={handleSaveEmail}
            disabled={updateProfile.isPending}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm text-white transition-colors"
          >
            {updateProfile.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            Save
          </button>
        </div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Key size={16} className="text-gray-400" />
          Change Password
        </h2>
        {pwdError && (
          <div className="flex items-center gap-2 text-sm text-red-400 bg-red-900/30 rounded p-2 mb-3">
            <AlertCircle size={14} /> {pwdError}
          </div>
        )}
        {changePassword.isSuccess && (
          <div className="flex items-center gap-2 text-sm text-green-400 bg-green-900/30 rounded p-2 mb-3">
            <CheckCircle size={14} /> Password changed successfully
          </div>
        )}
        <div className="space-y-3">
          <input
            type="password"
            value={oldPwd}
            onChange={(e) => setOldPwd(e.target.value)}
            placeholder="Current password"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />
          <input
            type="password"
            value={newPwd}
            onChange={(e) => setNewPwd(e.target.value)}
            placeholder="New password (min 6 chars)"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />
          <input
            type="password"
            value={pwdConfirm}
            onChange={(e) => setPwdConfirm(e.target.value)}
            placeholder="Confirm new password"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={handleChangePassword}
            disabled={changePassword.isPending || !oldPwd || !newPwd || !pwdConfirm}
            className="w-full flex items-center justify-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm text-white transition-colors"
          >
            {changePassword.isPending ? <Loader2 size={14} className="animate-spin" /> : <Key size={14} />}
            Change Password
          </button>
        </div>
      </div>
    </div>
  );
}
