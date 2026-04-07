import type { VerificationFilterType } from "@/store/slices/types";

interface VerificationFilterProps {
  value: VerificationFilterType;
  onChange: (value: VerificationFilterType) => void;
}

const filterOptions: { value: VerificationFilterType; label: string; title: string }[] = [
  { value: "all", label: "All", title: "Show all screenshots" },
  { value: "not_verified_by_me", label: "Unverified by Me", title: "Screenshots I haven't verified yet" },
  { value: "verified_by_me", label: "Verified by Me", title: "Screenshots I have verified" },
  { value: "verified_by_others", label: "Verified by Others", title: "Screenshots verified by others but not by me" },
  { value: "totals_mismatch", label: "Needs Attention", title: "Screenshots with bar/OCR total mismatch or missing app title" },
];

export const VerificationFilter = ({ value, onChange }: VerificationFilterProps) => {
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
          title={option.title}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
};
