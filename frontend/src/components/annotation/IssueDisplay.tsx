import type { ProcessingIssue } from "@/types";

interface IssueDisplayProps {
  issues: ProcessingIssue[];
  className?: string;
}

const getIssueStyle = (severity: "blocking" | "non_blocking") => {
  if (severity === "blocking") {
    return {
      container: "bg-red-100 border-red-500 text-red-800 dark:bg-red-900/30 dark:border-red-600 dark:text-red-300",
      badge: "bg-red-500 text-white",
      icon: "!",
    };
  }
  return {
    container: "bg-orange-100 border-orange-500 text-orange-800 dark:bg-orange-900/30 dark:border-orange-600 dark:text-orange-300",
    badge: "bg-orange-500 text-white",
    icon: "?",
  };
};

const getIssueTypeName = (issueType: string): string => {
  const typeMap: Record<string, string> = {
    GraphDetectionIssue: "Grid Detection Failed",
    TitleMissingIssue: "Title Missing",
    TotalNotFoundIssue: "Total Not Found",
    TotalParseErrorIssue: "Total Parse Error",
    TotalUnderestimationSmallIssue: "Minor Underestimation",
    TotalUnderestimationLargeIssue: "Large Underestimation",
    TotalOverestimationSmallIssue: "Minor Overestimation",
    TotalOverestimationLargeIssue: "Large Overestimation",
    ProcessingError: "Processing Error",
  };
  return typeMap[issueType] || issueType;
};

export const IssueDisplay = ({ issues, className = "" }: IssueDisplayProps) => {
  if (!issues || issues.length === 0) {
    return null;
  }

  const blockingIssues = issues.filter((i) => i.severity === "blocking");
  const nonBlockingIssues = issues.filter((i) => i.severity === "non_blocking");

  return (
    <div className={`space-y-3 ${className}`}>
      {blockingIssues.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-red-700 dark:text-red-400 flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center font-bold">
              !
            </span>
            Blocking Issues ({blockingIssues.length})
          </h4>
          {blockingIssues.map((issue, index) => {
            const style = getIssueStyle(issue.severity);
            return (
              <div
                key={index}
                className={`p-3 rounded-lg border-l-4 ${style.container}`}
              >
                <div className="flex items-start gap-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${style.badge}`}
                  >
                    {getIssueTypeName(issue.issue_type)}
                  </span>
                </div>
                <p className="mt-2 text-sm">
                  {issue.message || issue.description}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {nonBlockingIssues.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-orange-700 dark:text-orange-400 flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-orange-500 text-white text-xs flex items-center justify-center font-bold">
              ?
            </span>
            Warnings ({nonBlockingIssues.length})
          </h4>
          {nonBlockingIssues.map((issue, index) => {
            const style = getIssueStyle(issue.severity);
            return (
              <div
                key={index}
                className={`p-3 rounded-lg border-l-4 ${style.container}`}
              >
                <div className="flex items-start gap-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${style.badge}`}
                  >
                    {getIssueTypeName(issue.issue_type)}
                  </span>
                </div>
                <p className="mt-2 text-sm">
                  {issue.message || issue.description}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

interface ProcessingStatusBadgeProps {
  status: string;
}

export const ProcessingStatusBadge = ({
  status,
}: ProcessingStatusBadgeProps) => {
  const getStatusStyle = () => {
    switch (status) {
      case "completed":
        return "bg-green-100 text-green-800 border-green-300 dark:bg-green-900/30 dark:text-green-300 dark:border-green-600";
      case "skipped":
        return "bg-slate-100 text-slate-800 border-slate-300 dark:bg-slate-700 dark:text-slate-300 dark:border-slate-600";
      case "failed":
        return "bg-red-100 text-red-800 border-red-300 dark:bg-red-900/30 dark:text-red-300 dark:border-red-600";
      case "pending":
      default:
        return "bg-primary-100 text-primary-800 border-primary-300 dark:bg-primary-900/30 dark:text-primary-300 dark:border-primary-600";
    }
  };

  const getStatusLabel = () => {
    switch (status) {
      case "completed":
        return "Auto-Processed";
      case "skipped":
        return "Skipped";
      case "failed":
        return "Failed";
      case "pending":
      default:
        return "Pending";
    }
  };

  return (
    <span
      className={`px-2 py-1 text-xs font-medium rounded border ${getStatusStyle()}`}
    >
      {getStatusLabel()}
    </span>
  );
};
