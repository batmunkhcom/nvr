import { PersonStanding, Car, PawPrint, Tractor } from "lucide-react";
import type { CounterSummary } from "../../hooks/useCounters";

const cards = [
  { icon: PersonStanding, label: "Persons", key: "person" as const, color: "text-green-400" },
  { icon: Car, label: "Vehicles", key: "vehicle" as const, color: "text-blue-400" },
  { icon: PawPrint, label: "Animals", key: "animal" as const, color: "text-yellow-400" },
  { icon: Tractor, label: "Livestock", key: "livestock" as const, color: "text-purple-400" },
];

export default function CounterCards({ data, periodLabel = "today" }: { data: CounterSummary; periodLabel?: string }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {cards.map((card) => {
        const Icon = card.icon;
        const value = data[card.key] ?? 0;
        return (
          <div key={card.key} className="bg-gray-900 rounded border border-gray-800 p-3">
            <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
              <Icon size={14} className={card.color} /> {card.label}
            </div>
            <div className="text-lg font-bold">{value.toLocaleString()}</div>
            <div className="text-[10px] text-gray-500 mt-0.5">{periodLabel}</div>
          </div>
        );
      })}
    </div>
  );
}
