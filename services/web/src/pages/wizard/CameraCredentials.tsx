import { useWizardStore } from "../../store/wizardStore";
import { Eye, EyeOff, Camera } from "lucide-react";
import { useState } from "react";

export default function WizardCredentials() {
  const { selectedCameras, updateCredential, goNext, goBack } = useWizardStore();
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({});

  const toggleShow = (id: string) =>
    setShowPasswords((p) => ({ ...p, [id]: !p[id] }));

  if (!selectedCameras.length) {
    return (
      <div className="max-w-xl mx-auto mt-12 text-center">
        <p className="text-gray-400">No cameras selected. Go back and select cameras first.</p>
        <button onClick={goBack} className="mt-4 px-4 py-2 bg-gray-800 rounded-lg">Back</button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto mt-8">
      <h2 className="text-2xl font-bold mb-2">Camera Credentials</h2>
      <p className="text-gray-400 mb-6">Enter login credentials for each camera.</p>

      <div className="space-y-4">
        {selectedCameras.map((entry) => (
          <div key={entry.camera.id} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <div className="flex items-center gap-2 mb-3">
              <Camera size={16} className="text-gray-500" />
              <p className="text-sm font-semibold">{entry.camera.name || entry.camera.ip_address}</p>
              <span className="text-xs text-gray-600">{entry.camera.ip_address}</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Username</label>
                <input
                  type="text"
                  value={entry.username}
                  onChange={(e) => updateCredential(entry.camera.id, "username", e.target.value)}
                  placeholder="admin"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Password</label>
                <div className="relative">
                  <input
                    type={showPasswords[entry.camera.id] ? "text" : "password"}
                    value={entry.password}
                    onChange={(e) => updateCredential(entry.camera.id, "password", e.target.value)}
                    placeholder="••••••••"
                    className="w-full px-3 py-2 pr-8 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                  />
                  <button
                    onClick={() => toggleShow(entry.camera.id)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                  >
                    {showPasswords[entry.camera.id] ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-3 mt-6">
        <button onClick={goBack} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300">Back</button>
        <button onClick={goNext} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white">Next: Recording Settings</button>
      </div>
    </div>
  );
}
