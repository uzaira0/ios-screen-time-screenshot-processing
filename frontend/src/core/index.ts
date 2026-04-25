export type {
  IScreenshotService,
  IAnnotationService,
  IConsensusService,
  IStorageService,
  IProcessingService,
  ProcessingConfig,
  ProcessingProgressCallback,
} from "./interfaces";

// Re-export types from the canonical types location
export type {
  User,
  LoginCredentials,
  AuthResponse,
  ProcessingStatus,
  ProcessingIssue,
  Screenshot,
  GridCoordinates,
  Point,
  HourlyData,
  HourlyValues,
  Annotation,
  AnnotationCreate,
  Consensus,
  QueueStats,
  ProcessingResult,
  ReprocessRequest,
  ApiError,
  ImageType,
  ScreenshotListResponse,
  ScreenshotListParams,
  NavigationResponse,
  NavigationParams,
  ProcessingProgress,
  Group,
  AnnotationStatus,
  ProcessingMethod,
} from "@/types";

// Re-export utility functions
export {
  screenshotToGridCoordinates,
  annotationToGridCoordinates,
  gridCoordinatesToFlat,
  gridCoordinatesToPoints,
  IMAGE_TYPES,
  PROCESSING_STATUSES,
  ANNOTATION_STATUSES,
  PROCESSING_METHODS,
} from "@/types";

export { ServiceContainer, TOKENS, bootstrapServices } from "./di";
export type { ServiceToken } from "./di";

export type { AppMode, AppConfig } from "./config";
export { detectMode, createConfig } from "./config";

export {
  ServiceProvider,
  ServiceContext,
  useScreenshotService,
  useAnnotationService,
  useConsensusService,
  useStorageService,
  useProcessingService,
  usePreprocessingPipelineService,
  useFeatures,
  useActiveStages,
} from "./hooks";
