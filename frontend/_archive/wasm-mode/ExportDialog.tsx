import React, { useState } from 'react';
import { DataExportService } from '@/core/implementations/wasm/storage/ExportService';
import toast from 'react-hot-toast';

interface ExportDialogProps {
  isOpen: boolean;
  onClose: () => void;
  screenshotId?: number;
}

type ExportFormat = 'csv' | 'excel' | 'json' | 'backup';
type ExportScope = 'all' | 'current';

export const ExportDialog: React.FC<ExportDialogProps> = ({
  isOpen,
  onClose,
  screenshotId,
}) => {
  const [format, setFormat] = useState<ExportFormat>('csv');
  const [scope, setScope] = useState<ExportScope>(screenshotId ? 'current' : 'all');
  const [isExporting, setIsExporting] = useState(false);
  const [exportService] = useState(() => new DataExportService());

  if (!isOpen) return null;

  const handleExport = async () => {
    setIsExporting(true);

    try {
      switch (format) {
        case 'csv':
          if (scope === 'current' && screenshotId) {
            await exportService.downloadAnnotationsCSV();
          } else {
            await exportService.downloadAnnotationsCSV();
          }
          toast.success('CSV exported successfully');
          break;

        case 'excel':
          if (scope === 'current' && screenshotId) {
            await exportService.downloadAnnotationsExcel();
          } else {
            await exportService.downloadExcel();
          }
          toast.success('Excel file exported successfully');
          break;

        case 'json':
          await exportService.downloadJSON();
          toast.success('JSON exported successfully');
          break;

        case 'backup':
          await exportService.downloadBackup();
          toast.success('Backup created successfully');
          break;

        default:
          toast.error('Unknown export format');
      }

      onClose();
    } catch (error) {
      console.error('Export failed:', error);
      toast.error(`Export failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsExporting(false);
    }
  };

  const formatOptions: Array<{ value: ExportFormat; label: string; description: string; icon: string }> = [
    {
      value: 'csv',
      label: 'CSV',
      description: 'Comma-separated values, great for Excel and data analysis',
      icon: '📊',
    },
    {
      value: 'excel',
      label: 'Excel',
      description: 'Microsoft Excel format with multiple sheets',
      icon: '📈',
    },
    {
      value: 'json',
      label: 'JSON',
      description: 'Complete database export for advanced users',
      icon: '📄',
    },
    {
      value: 'backup',
      label: 'Backup',
      description: 'Full backup including all data and settings',
      icon: '💾',
    },
  ];

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-gray-900">Export Data</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
              aria-label="Close dialog"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-3">
                Export Format
              </label>
              <div className="grid grid-cols-2 gap-3">
                {formatOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => setFormat(option.value)}
                    className={`
                      flex flex-col items-start p-4 rounded-lg border-2 transition-all text-left
                      ${
                        format === option.value
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 bg-white hover:border-gray-300'
                      }
                    `}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-2xl">{option.icon}</span>
                      <span className="font-medium text-sm">{option.label}</span>
                    </div>
                    <span className="text-xs text-gray-600">{option.description}</span>
                  </button>
                ))}
              </div>
            </div>

            {screenshotId && format !== 'backup' && format !== 'json' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Export Scope
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={() => setScope('current')}
                    className={`
                      p-4 rounded-lg border-2 transition-all
                      ${
                        scope === 'current'
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 bg-white hover:border-gray-300'
                      }
                    `}
                  >
                    <div className="font-medium text-sm mb-1">Current Screenshot</div>
                    <div className="text-xs text-gray-600">
                      Export only this screenshot's data
                    </div>
                  </button>
                  <button
                    onClick={() => setScope('all')}
                    className={`
                      p-4 rounded-lg border-2 transition-all
                      ${
                        scope === 'all'
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 bg-white hover:border-gray-300'
                      }
                    `}
                  >
                    <div className="font-medium text-sm mb-1">All Data</div>
                    <div className="text-xs text-gray-600">
                      Export all screenshots and annotations
                    </div>
                  </button>
                </div>
              </div>
            )}

            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <div className="flex items-start gap-2">
                <svg
                  className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                    clipRule="evenodd"
                  />
                </svg>
                <div className="text-sm text-blue-900">
                  <p className="font-medium mb-1">Privacy Note:</p>
                  <p>
                    {format === 'backup' || format === 'json'
                      ? 'This export includes all your data and can be used to restore your entire database.'
                      : 'This export contains only annotation and screenshot metadata. No sensitive information is included.'}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="flex gap-3 justify-end mt-6 pt-6 border-t border-gray-200">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors font-medium"
              disabled={isExporting}
            >
              Cancel
            </button>
            <button
              onClick={handleExport}
              disabled={isExporting}
              className="px-4 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isExporting ? (
                <>
                  <svg
                    className="animate-spin h-5 w-5"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  <span>Exporting...</span>
                </>
              ) : (
                <>
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  <span>Export</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
