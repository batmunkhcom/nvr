import LocationsSection from "../components/layout/LocationsSection";

export default function Settings() {
  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Settings</h1>

      <section className="bg-gray-900 rounded border border-gray-800 p-6">
        <LocationsSection />
      </section>
    </div>
  );
}
