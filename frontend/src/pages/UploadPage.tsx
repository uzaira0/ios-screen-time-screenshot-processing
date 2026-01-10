import { Layout } from "@/components/layout/Layout";
import { BrowserUpload } from "@/components/preprocessing/BrowserUpload";

export const UploadPage = () => {
  return (
    <Layout>
      <div className="max-w-7xl mx-auto px-4 py-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">
          Upload Screenshots
        </h1>
        <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-6">
          <BrowserUpload />
        </div>
      </div>
    </Layout>
  );
};
