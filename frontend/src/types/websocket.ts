export interface WebSocketEvent {
  type: string;
  timestamp: string;
  data: unknown;
}

export interface AnnotationSubmittedEvent {
  screenshot_id: number;
  user_id: number;
  username: string;
  annotation_count: number;
  required_count: number;
  has_consensus: boolean;
}

export interface ConsensusDisputedEvent {
  screenshot_id: number;
  filename: string;
  disagreement_count: number;
}

export interface ScreenshotCompletedEvent {
  screenshot_id: number;
  filename: string;
  annotation_count: number;
}

export interface UserJoinedEvent {
  user_id: number;
  username: string;
  active_users: number;
}

export interface UserLeftEvent {
  user_id: number;
  username: string;
  active_users: number;
}
