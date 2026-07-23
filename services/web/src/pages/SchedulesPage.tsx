import RecordingSchedulesSection from "../components/config/RecordingSchedulesSection";

export default function SchedulesPage() {
  return (
    <div className="page-enter">
      <h1 className="text-2xl font-bold text-white mb-6">Recording Schedules</h1>
      <div className="max-w-3xl">
        <RecordingSchedulesSection />
      </div>
    </div>
  );
}
