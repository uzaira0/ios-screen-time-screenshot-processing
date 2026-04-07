import { exportDB, importInto } from "dexie-export-import";
import type { ExportProgress } from "dexie-export-import";
import { db } from "./database";
import type { Annotation } from "../../../models";
import * as XLSX from "xlsx";

export interface ImportProgress {
  totalTables: number;
  completedTables: number;
  totalRows: number | undefined;
  completedRows: number;
  done: boolean;
}

export type { ExportProgress };

export class DataExportService {
  async exportToJSON(options?: {
    prettyJson?: boolean;
    progressCallback?: (progress: ExportProgress) => boolean;
  }): Promise<Blob> {
    try {
      const blob = await exportDB(db, {
        prettyJson: options?.prettyJson ?? false,
        progressCallback: options?.progressCallback,
      });

      return blob;
    } catch (error) {
      console.error("Failed to export database to JSON:", error);
      throw error;
    }
  }

  async exportAnnotationsToCSV(screenshotId?: number): Promise<Blob> {
    try {
      let annotations: Annotation[];

      if (screenshotId !== undefined) {
        annotations = await db.annotations
          .where("screenshot_id")
          .equals(screenshotId)
          .toArray();
      } else {
        annotations = await db.annotations.toArray();
      }

      const screenshots = await db.screenshots.toArray();
      const screenshotMap = new Map(screenshots.map((s) => [s.id, s]));

      const csvRows: string[] = [];

      // Header row
      const hourHeaders = Array.from({ length: 24 }, (_, i) => i.toString());
      csvRows.push(
        [
          "Filepath",
          "Filename",
          "Participant ID",
          "Date",
          "App Title",
          ...hourHeaders,
          "Total",
        ].join(","),
      );

      for (const annotation of annotations) {
        const screenshot = screenshotMap.get(annotation.screenshot_id);
        const filePath = screenshot?.file_path || "";
        const filename = filePath.split(/[/\\]/).pop() || "";
        const date = annotation.created_at
          ? annotation.created_at.split("T")[0]
          : "";
        const appTitle = screenshot?.extracted_title || "";

        const hourlyData = annotation.hourly_values || {};

        // Build array of 24 hourly values (0-23)
        const hourlyValues = Array.from({ length: 24 }, (_, hour) => {
          const value = hourlyData[hour.toString()] ?? hourlyData[hour] ?? "";
          return value;
        });

        // Calculate total from hourly values
        const total = hourlyValues.reduce((sum: number, val) => {
          const num =
            typeof val === "number" ? val : parseInt(val as string, 10);
          return sum + (isNaN(num) ? 0 : num);
        }, 0);

        const participantId = screenshot?.participant_id || "";

        const row = [
          filePath ? `"${filePath.replace(/"/g, '""')}"` : "",
          filename ? `"${filename.replace(/"/g, '""')}"` : "",
          participantId ? `"${participantId.replace(/"/g, '""')}"` : "",
          date,
          appTitle ? `"${appTitle.replace(/"/g, '""')}"` : "",
          ...hourlyValues,
          total,
        ].join(",");

        csvRows.push(row);
      }

      const csvContent = csvRows.join("\n");
      return new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    } catch (error) {
      console.error("Failed to export annotations to CSV:", error);
      throw error;
    }
  }

  async exportScreenshotsToCSV(): Promise<Blob> {
    try {
      const screenshots = await db.screenshots.toArray();

      const csvRows: string[] = [];

      csvRows.push(
        "ID,File Path,Image Type,Status,Processing Status,Uploaded At,Has Blocking Issues,Extracted Title,Extracted Total,Annotation Count",
      );

      for (const screenshot of screenshots) {
        const row = [
          screenshot.id,
          screenshot.file_path
            ? `"${screenshot.file_path.replace(/"/g, '""')}"`
            : "",
          screenshot.image_type,
          screenshot.annotation_status,
          screenshot.processing_status,
          screenshot.uploaded_at,
          screenshot.has_blocking_issues,
          screenshot.extracted_title
            ? `"${screenshot.extracted_title.replace(/"/g, '""')}"`
            : "",
          screenshot.extracted_total || "",
          screenshot.current_annotation_count,
        ].join(",");

        csvRows.push(row);
      }

      const csvContent = csvRows.join("\n");
      return new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    } catch (error) {
      console.error("Failed to export screenshots to CSV:", error);
      throw error;
    }
  }

  async importFromJSON(
    jsonBlob: Blob,
    options?: {
      clearTablesBeforeImport?: boolean;
      progressCallback?: (progress: ImportProgress) => boolean;
    },
  ): Promise<void> {
    try {
      await importInto(db, jsonBlob, {
        clearTablesBeforeImport: options?.clearTablesBeforeImport ?? false,
        acceptVersionDiff: true,
        acceptNameDiff: false,
        acceptMissingTables: false,
        acceptChangedPrimaryKey: false,
        overwriteValues: true,
        progressCallback: options?.progressCallback,
      });
    } catch (error) {
      console.error("Failed to import database from JSON:", error);
      throw error;
    }
  }

  async createBackup(): Promise<Blob> {
    const blob = await this.exportToJSON({ prettyJson: false });

    return blob;
  }

  async restoreBackup(
    backupBlob: Blob,
    options?: {
      clearExisting?: boolean;
      progressCallback?: (progress: ImportProgress) => boolean;
    },
  ): Promise<void> {
    try {
      await this.importFromJSON(backupBlob, {
        clearTablesBeforeImport: options?.clearExisting ?? true,
        progressCallback: options?.progressCallback,
      });
    } catch (error) {
      console.error("Failed to restore backup:", error);
      throw error;
    }
  }

  async downloadBlob(blob: Blob, filename: string): Promise<void> {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async downloadJSON(filename?: string): Promise<void> {
    const blob = await this.exportToJSON({ prettyJson: true });
    const defaultFilename = `screenshot-processor-export-${new Date().toISOString().split("T")[0]}.json`;
    await this.downloadBlob(blob, filename || defaultFilename);
  }

  async downloadAnnotationsCSV(filename?: string): Promise<void> {
    const blob = await this.exportAnnotationsToCSV();
    const defaultFilename = `annotations-export-${new Date().toISOString().split("T")[0]}.csv`;
    await this.downloadBlob(blob, filename || defaultFilename);
  }

  async downloadScreenshotsCSV(filename?: string): Promise<void> {
    const blob = await this.exportScreenshotsToCSV();
    const defaultFilename = `screenshots-export-${new Date().toISOString().split("T")[0]}.csv`;
    await this.downloadBlob(blob, filename || defaultFilename);
  }

  async downloadBackup(): Promise<void> {
    const blob = await this.createBackup();
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const filename = `screenshot-processor-backup-${timestamp}.json`;
    await this.downloadBlob(blob, filename);
  }

  async exportToExcel(screenshotId?: number): Promise<Blob> {
    try {
      let annotations: Annotation[];

      if (screenshotId !== undefined) {
        annotations = await db.annotations
          .where("screenshot_id")
          .equals(screenshotId)
          .toArray();
      } else {
        annotations = await db.annotations.toArray();
      }

      const screenshots = await db.screenshots.toArray();
      const screenshotMap = new Map(screenshots.map((s) => [s.id, s]));

      const workbook = XLSX.utils.book_new();

      // Build annotation rows with hourly columns
      const annotationRows = annotations.map((annotation) => {
        const screenshot = screenshotMap.get(annotation.screenshot_id);
        const filePath = screenshot?.file_path || "";
        const filename = filePath.split(/[/\\]/).pop() || "";
        const date = annotation.created_at
          ? annotation.created_at.split("T")[0]
          : "";
        const appTitle = screenshot?.extracted_title || "";

        const hourlyData = annotation.hourly_values || {};

        // Build hourly columns object
        const hourlyColumns: Record<string, number | string> = {};
        let total = 0;
        for (let hour = 0; hour < 24; hour++) {
          const value = hourlyData[hour.toString()] ?? hourlyData[hour] ?? "";
          hourlyColumns[hour.toString()] = value;
          const num =
            typeof value === "number" ? value : parseInt(value as string, 10);
          if (!isNaN(num)) total += num;
        }

        return {
          Filepath: filePath,
          Filename: filename,
          "Participant ID": screenshot?.participant_id || "",
          Date: date,
          "App Title": appTitle,
          ...hourlyColumns,
          Total: total,
        };
      });

      const annotationSheet = XLSX.utils.json_to_sheet(annotationRows);
      XLSX.utils.book_append_sheet(workbook, annotationSheet, "Annotations");

      const screenshotRows = screenshots.map((screenshot) => ({
        ID: screenshot.id,
        "File Path": screenshot.file_path || "",
        "Image Type": screenshot.image_type,
        Status: screenshot.annotation_status,
        "Processing Status": screenshot.processing_status,
        "Uploaded At": screenshot.uploaded_at,
        "Has Blocking Issues": screenshot.has_blocking_issues,
        "Extracted Title": screenshot.extracted_title || "",
        "Extracted Total": screenshot.extracted_total || "",
        "Annotation Count": screenshot.current_annotation_count,
      }));

      const screenshotSheet = XLSX.utils.json_to_sheet(screenshotRows);
      XLSX.utils.book_append_sheet(workbook, screenshotSheet, "Screenshots");

      const excelBuffer = XLSX.write(workbook, {
        type: "array",
        bookType: "xlsx",
      });
      return new Blob([excelBuffer], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
    } catch (error) {
      console.error("Failed to export to Excel:", error);
      throw error;
    }
  }

  async downloadExcel(filename?: string): Promise<void> {
    const blob = await this.exportToExcel();
    const defaultFilename = `screenshot-processor-export-${new Date().toISOString().split("T")[0]}.xlsx`;
    await this.downloadBlob(blob, filename || defaultFilename);
  }

  async exportAnnotationsToExcel(screenshotId?: number): Promise<Blob> {
    try {
      let annotations: Annotation[];

      if (screenshotId !== undefined) {
        annotations = await db.annotations
          .where("screenshot_id")
          .equals(screenshotId)
          .toArray();
      } else {
        annotations = await db.annotations.toArray();
      }

      const screenshots = await db.screenshots.toArray();
      const screenshotMap = new Map(screenshots.map((s) => [s.id, s]));

      const workbook = XLSX.utils.book_new();

      // Build rows with hourly columns
      const rows = annotations.map((annotation) => {
        const screenshot = screenshotMap.get(annotation.screenshot_id);
        const filePath = screenshot?.file_path || "";
        const filename = filePath.split(/[/\\]/).pop() || "";
        const date = annotation.created_at
          ? annotation.created_at.split("T")[0]
          : "";
        const appTitle = screenshot?.extracted_title || "";

        const hourlyData = annotation.hourly_values || {};

        // Build hourly columns object
        const hourlyColumns: Record<string, number | string> = {};
        let total = 0;
        for (let hour = 0; hour < 24; hour++) {
          const value = hourlyData[hour.toString()] ?? hourlyData[hour] ?? "";
          hourlyColumns[hour.toString()] = value;
          const num =
            typeof value === "number" ? value : parseInt(value as string, 10);
          if (!isNaN(num)) total += num;
        }

        return {
          Filepath: filePath,
          Filename: filename,
          "Participant ID": screenshot?.participant_id || "",
          Date: date,
          "App Title": appTitle,
          ...hourlyColumns,
          Total: total,
        };
      });

      const worksheet = XLSX.utils.json_to_sheet(rows);
      XLSX.utils.book_append_sheet(workbook, worksheet, "Annotations");

      const excelBuffer = XLSX.write(workbook, {
        type: "array",
        bookType: "xlsx",
      });
      return new Blob([excelBuffer], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
    } catch (error) {
      console.error("Failed to export annotations to Excel:", error);
      throw error;
    }
  }

  async downloadAnnotationsExcel(filename?: string): Promise<void> {
    const blob = await this.exportAnnotationsToExcel();
    const defaultFilename = `annotations-export-${new Date().toISOString().split("T")[0]}.xlsx`;
    await this.downloadBlob(blob, filename || defaultFilename);
  }
}
