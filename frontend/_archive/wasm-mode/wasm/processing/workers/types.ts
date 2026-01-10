import type {
  GridCoordinates,
  HourlyData,
} from "../../../../models";
import type { ImageType } from "@/types";

// Message payload types
export type WorkerMessagePayload =
  | InitializePayload
  | ProcessImagePayload
  | ExtractTitlePayload
  | ExtractTotalPayload
  | ExtractHourlyDataPayload
  | DetectGridPayload;

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export interface InitializePayload {}

export interface ProcessImagePayload {
  imageData: ImageData;
  imageType: ImageType;
  gridCoordinates?: GridCoordinates;
}

export interface ExtractTitlePayload {
  imageData: ImageData;
}

export interface ExtractTotalPayload {
  imageData: ImageData;
}

export interface ExtractHourlyDataPayload {
  imageData: ImageData;
  gridCoordinates: GridCoordinates;
  imageType: ImageType;
}

export interface DetectGridPayload {
  imageData: ImageData;
  imageType: ImageType;
}

export interface WorkerMessage {
  type: string;
  id: string;
  payload: WorkerMessagePayload;
}

export interface InitializeMessage extends WorkerMessage {
  type: "INITIALIZE";
  payload: InitializePayload;
}

export interface ProcessImageMessage extends WorkerMessage {
  type: "PROCESS_IMAGE";
  payload: ProcessImagePayload;
}

export interface ExtractTitleMessage extends WorkerMessage {
  type: "EXTRACT_TITLE";
  payload: ExtractTitlePayload;
}

export interface ExtractTotalMessage extends WorkerMessage {
  type: "EXTRACT_TOTAL";
  payload: ExtractTotalPayload;
}

export interface ExtractHourlyDataMessage extends WorkerMessage {
  type: "EXTRACT_HOURLY_DATA";
  payload: ExtractHourlyDataPayload;
}

export interface DetectGridMessage extends WorkerMessage {
  type: "DETECT_GRID";
  payload: DetectGridPayload;
}

// Response payload types
export type WorkerResponsePayload =
  | ProcessImageResponsePayload
  | ProgressPayload
  | InitializeCompletePayload
  | ExtractTitleResponsePayload
  | ExtractTotalResponsePayload
  | ExtractHourlyDataResponsePayload
  | DetectGridResponsePayload;

export interface ProcessImageResponsePayload {
  hourlyData: HourlyData;
  title: string | null;
  total: string | null;
  gridCoordinates?: GridCoordinates;
  gridDetectionFailed?: boolean;
  gridDetectionError?: string;
}

export interface ProgressPayload {
  stage:
    | "loading"
    | "preprocessing"
    | "ocr_title"
    | "ocr_total"
    | "ocr_hourly"
    | "complete";
  progress: number;
  message?: string;
}

export interface InitializeCompletePayload {
  initialized: boolean;
}

export interface ExtractTitleResponsePayload {
  title: string | null;
}

export interface ExtractTotalResponsePayload {
  total: string | null;
}

export interface ExtractHourlyDataResponsePayload {
  hourlyData: HourlyData;
}

export interface DetectGridResponsePayload {
  gridCoordinates: GridCoordinates | null;
}

export interface WorkerResponse {
  type: string;
  id: string;
  payload?: WorkerResponsePayload;
  error?: string;
}

export interface ProcessImageResponse extends WorkerResponse {
  type: "PROCESS_IMAGE_COMPLETE";
  payload: ProcessImageResponsePayload;
}

export interface ProgressUpdate extends WorkerResponse {
  type: "PROGRESS";
  payload: ProgressPayload;
}

export interface ErrorResponse extends WorkerResponse {
  type: "ERROR";
  error: string;
}
