import { useNavigate } from "react-router-dom";
import { useWizardStore } from "../../store/wizardStore";
import { Camera, Video } from "lucide-react";

export default function WizardWelcome() {
  const navigate = useNavigate();
  const goNext = useWizardStore((s) => s.goNext);

  return (
    <div className="max-w-2xl mx-auto mt-20 text-center">
      <div className="flex justify-center gap-4 mb-6">
        <Video size={48} className="text-blue-400" />
        <Camera size={48} className="text-blue-400" />
      </div>
      <h1 className="text-3xl font-bold mb-3">NVR Setup Wizard</h1>
      <p className="text-gray-400 mb-8 max-w-md mx-auto">
        Let's get your cameras set up. The wizard will scan your network,
        discover available cameras, and configure recording settings.
      </p>
      <div className="flex gap-3 justify-center">
        <button
          onClick={goNext}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium text-white"
        >
          Get Started
        </button>
        <button
          onClick={() => navigate("/cameras")}
          className="px-6 py-2.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
        >
          Skip — Manual Setup
        </button>
      </div>
      <div className="mt-12 grid grid-cols-3 gap-4 text-sm text-gray-500">
        <div className="p-3 bg-gray-900 rounded-lg border border-gray-800">
          <p className="font-semibold text-gray-300 mb-1">Auto-Discovery</p>
          <p>Scan your network for ONVIF and RTSP cameras</p>
        </div>
        <div className="p-3 bg-gray-900 rounded-lg border border-gray-800">
          <p className="font-semibold text-gray-300 mb-1">Configure</p>
          <p>Set credentials and stream settings per camera</p>
        </div>
        <div className="p-3 bg-gray-900 rounded-lg border border-gray-800">
          <p className="font-semibold text-gray-300 mb-1">Start Recording</p>
          <p>Recording begins automatically after setup</p>
        </div>
      </div>
    </div>
  );
}
