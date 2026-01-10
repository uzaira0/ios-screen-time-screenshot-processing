import {
  FILTER_STATUSES,
  FILTER_STATUS_LABELS,
  type FilterStatus,
} from "@/constants/processingStatus";

interface ProcessingStatusFilterProps {
  value: FilterStatus | "all";
  onChange: (value: FilterStatus | "all") => void;
}

const filterOptions: { value: FilterStatus | "all"; label: string }[] = [
  { value: "all", label: "All Statuses" },
  ...FILTER_STATUSES.map((status) => ({
    value: status,
    label: FILTER_STATUS_LABELS[status],
  })),
];

export const ProcessingStatusFilter = ({
  value,
  onChange,
}: ProcessingStatusFilterProps) => {
  return (
    <div className="flex gap-1 flex-wrap">
      {filterOptions.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            value === option.value
              ? "bg-primary-600 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-400 dark:hover:bg-slate-600"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
};
