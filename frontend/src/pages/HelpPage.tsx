import { Layout } from "@/components/layout/Layout";

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-6">
    <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">{title}</h2>
    {children}
  </div>
);

export const HelpPage = () => {
  return (
    <Layout>
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Help</h1>

        <Section title="Getting Started">
          <ol className="list-decimal list-inside space-y-2 text-sm text-slate-700 dark:text-slate-300">
            <li>
              <span className="font-medium">Upload</span> iOS Screen Time screenshots — the hourly bar graph page, not the daily summary.
            </li>
            <li>
              <span className="font-medium">Review</span> auto-extracted data in the annotation view: grid alignment, hourly values, and app title.
            </li>
            <li>
              <span className="font-medium">Verify or correct</span> the data, then export as CSV.
            </li>
          </ol>
        </Section>

        <Section title="Annotation Guide">
          <ul className="space-y-2 text-sm text-slate-700 dark:text-slate-300">
            <li>
              The <span className="font-medium text-blue-600 dark:text-blue-400">grid</span> (blue rectangle) defines where the bar graph is. Drag corners to adjust.
            </li>
            <li>
              Each <span className="font-medium">bar</span> represents one hour (12AM-11PM). Values are minutes (0-60).
            </li>
            <li>
              <span className="font-medium">Title</span> is the app name shown above the graph (e.g., "Instagram", "YouTube").
            </li>
            <li>
              <span className="font-medium text-green-600 dark:text-green-400">Verify</span> confirms the data is correct. <span className="font-medium">Skip</span> marks it for later review.
            </li>
            <li>
              Color coding: <span className="text-green-600 dark:text-green-400">green</span> = matches consensus, <span className="text-yellow-600 dark:text-yellow-400">yellow</span> = minor difference, <span className="text-red-600 dark:text-red-400">red</span> = major difference.
            </li>
          </ul>
        </Section>

        <Section title="Preprocessing">
          <ul className="space-y-1.5 text-sm text-slate-700 dark:text-slate-300">
            <li><span className="font-medium">Device Detection</span> — Identifies iPad vs iPhone screenshots</li>
            <li><span className="font-medium">Cropping</span> — Removes iPad sidebar if present</li>
            <li><span className="font-medium">PHI Redaction</span> — Blacks out personal information (names, identifiers)</li>
            <li><span className="font-medium">OCR</span> — Extracts app title, total usage time, and hourly bar values</li>
          </ul>
        </Section>

        <Section title="Keyboard Shortcuts">
          <p className="text-sm text-slate-700 dark:text-slate-300">
            Press <kbd className="px-1.5 py-0.5 text-xs font-mono bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded">?</kbd> on any page to see available shortcuts.
          </p>
        </Section>

        <Section title="Export">
          <p className="text-sm text-slate-700 dark:text-slate-300">
            CSV export contains: screenshot ID, group, participant, date, app title, total, and 24 hourly values (h0-h23) in minutes.
          </p>
        </Section>
      </div>
    </Layout>
  );
};
