import { clsx } from "clsx";
import type { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: "none" | "sm" | "md" | "lg";
}

const paddingClasses = {
  none: "",
  sm: "p-3",
  md: "p-5",
  lg: "p-6",
};

export function Card({ children, className, padding = "md", ...props }: CardProps) {
  return (
    <div
      className={clsx(
        "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-sm",
        paddingClasses[padding],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
