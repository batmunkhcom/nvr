import { useWizardStore } from "../../store/wizardStore";
import WizardWelcome from "./Welcome";
import WizardDiscovery from "./AutoDiscovery";
import WizardReview from "./ReviewDevices";
import WizardCredentials from "./CameraCredentials";
import WizardRecordingSettings from "./RecordingSettings";
import WizardSummary from "./Summary";

const STEPS = ["Welcome", "Discovery", "Select", "Credentials", "Recording", "Summary"];

export default function WizardPage() {
  const step = useWizardStore((s) => s.step);

  const renderStep = () => {
    switch (step) {
      case 0: return <WizardWelcome />;
      case 1: return <WizardDiscovery />;
      case 2: return <WizardReview />;
      case 3: return <WizardCredentials />;
      case 4: return <WizardRecordingSettings />;
      case 5: return <WizardSummary />;
      default: return <WizardWelcome />;
    }
  };

  return (
    <div className="page-enter p-4 max-w-4xl mx-auto">
      {step > 0 && (
        <div className="flex items-center gap-2 mb-6">
          {STEPS.map((label, i) => (
            <div key={i} className="flex items-center gap-2">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                  i <= step ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-600"
                }`}
              >
                {i < step ? <span>&#10003;</span> : i + 1}
              </div>
              <span className={`text-xs ${i <= step ? "text-gray-300" : "text-gray-600"}`}>
                {label}
              </span>
              {i < STEPS.length - 1 && <div className="w-6 h-px bg-gray-700" />}
            </div>
          ))}
        </div>
      )}
      {renderStep()}
    </div>
  );
}
