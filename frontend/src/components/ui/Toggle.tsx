import { clsx } from "clsx";

interface ToggleProps {
  checked?: boolean;
  defaultChecked?: boolean;
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
}

export function Toggle({ checked, defaultChecked, onChange, disabled, label }: ToggleProps) {
  return (
    <label className={clsx("relative inline-flex items-center", disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer")}>
      <input
        type="checkbox"
        className="sr-only peer"
        checked={checked}
        defaultChecked={defaultChecked}
        onChange={onChange ? (e) => onChange(e.target.checked) : undefined}
        disabled={disabled}
        aria-label={label}
      />
      <div className="w-11 h-6 bg-slate-200 dark:bg-slate-600 peer-focus-visible:outline-none peer-focus-visible:ring-4 peer-focus-visible:ring-primary-300 dark:peer-focus-visible:ring-primary-800 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white dark:after:bg-slate-300 after:border-slate-300 dark:after:border-slate-500 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600" />
    </label>
  );
}
