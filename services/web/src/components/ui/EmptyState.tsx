import { Box } from "lucide-react";

interface Props {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export default function EmptyState({ icon, title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-16 h-16 mb-4 rounded-full bg-surface-2 flex items-center justify-center text-surface-border">
        {icon || <Box size={28} />}
      </div>
      <h3 className="text-sm font-medium text-gray-300 mb-1">{title}</h3>
      {description && <p className="text-xs text-gray-500 max-w-xs">{description}</p>}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 px-4 py-2 bg-accent hover:bg-accent-hover rounded text-sm text-white transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
