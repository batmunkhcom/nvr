import LocationsSection from "../components/layout/LocationsSection";

export default function LocationsPage() {
  return (
    <div className="page-enter">
      <h1 className="text-2xl font-bold text-white mb-6">Locations</h1>
      <div className="max-w-2xl">
        <LocationsSection />
      </div>
    </div>
  );
}
