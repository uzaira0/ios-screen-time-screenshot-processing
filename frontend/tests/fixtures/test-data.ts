/**
 * Test data fixtures for screenshots and annotations
 */

// Type definitions for test data
type ImageType = "screen_time" | "battery";
type ProcessingStatus = "pending" | "completed" | "failed" | "skipped";
type HourlyData = Record<number, number>;

interface ProcessingIssue {
  type: string;
  severity: string;
  message: string;
  field: string | null;
  value: string | number | null;
}

interface MockScreenshot {
  id: number;
  filename: string;
  image_type: ImageType;
  participant_id: string;
  group_id: string;
  processing_status: ProcessingStatus;
  current_annotation_count: number;
  target_annotations: number;
  extracted_title: string;
  extracted_total: string;
  extracted_hourly_data: HourlyData;
  grid_upper_left_x: number;
  grid_upper_left_y: number;
  grid_lower_right_x: number;
  grid_lower_right_y: number;
  has_blocking_issues: boolean;
  processing_issues: ProcessingIssue[];
  verified_by_user_ids: number[];
  created_at: string;
  uploaded_by_username: string;
}

interface MockGroup {
  id: string;
  name: string;
  image_type: ImageType;
  created_at: string;
  screenshot_count: number;
  processing_pending: number;
  processing_completed: number;
  processing_failed: number;
  processing_skipped: number;
}

export const mockScreenshot: MockScreenshot = {
  id: 1,
  filename: "test_screenshot.png",
  image_type: "screen_time",
  participant_id: "P001",
  group_id: "test-group",
  processing_status: "completed",
  current_annotation_count: 0,
  target_annotations: 1,
  extracted_title: "Instagram",
  extracted_total: "2h 30m",
  extracted_hourly_data: {
    0: 10,
    1: 15,
    2: 20,
    3: 25,
    4: 30,
    5: 35,
    6: 40,
    7: 45,
    8: 50,
    9: 55,
    10: 60,
    11: 50,
    12: 45,
    13: 40,
    14: 35,
    15: 30,
    16: 25,
    17: 20,
    18: 15,
    19: 10,
    20: 5,
    21: 0,
    22: 0,
    23: 0,
  },
  grid_upper_left_x: 100,
  grid_upper_left_y: 200,
  grid_lower_right_x: 800,
  grid_lower_right_y: 600,
  has_blocking_issues: false,
  processing_issues: [],
  verified_by_user_ids: [],
  created_at: new Date().toISOString(),
  uploaded_by_username: "admin",
};

export const mockGroup: MockGroup = {
  id: "test-group",
  name: "test-group",
  image_type: "screen_time",
  created_at: new Date().toISOString(),
  screenshot_count: 10,
  processing_pending: 3,
  processing_completed: 5,
  processing_failed: 1,
  processing_skipped: 1,
};

export const mockAnnotation = {
  id: 1,
  screenshot_id: 1,
  user_id: 1,
  username: "testuser",
  hourly_data: mockScreenshot.extracted_hourly_data,
  grid_coords: {
    upper_left: { x: 100, y: 200 },
    lower_right: { x: 800, y: 600 },
  },
  notes: "Test annotation",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  time_spent_seconds: 120,
};

export const mockQueueStats = {
  total: 10,
  pending: 3,
  completed: 5,
  skipped: 1,
  failed: 1,
  total_annotations: 5,
  avg_time_per_annotation: 120,
};

export const mockUser = {
  id: 1,
  username: "testuser",
  email: "test@example.com",
  role: "annotator",
  is_active: true,
  created_at: new Date().toISOString(),
  annotations_count: 10,
  avg_time_spent_seconds: 120,
};

/**
 * Helper to create test screenshot with custom properties
 */
export function createMockScreenshot(
  overrides: Partial<MockScreenshot> = {},
): MockScreenshot {
  return { ...mockScreenshot, ...overrides };
}

/**
 * Helper to create test group with custom properties
 */
export function createMockGroup(overrides: Partial<MockGroup> = {}): MockGroup {
  return { ...mockGroup, ...overrides };
}

/**
 * Helper to create test annotation with custom properties
 */
export function createMockAnnotation(
  overrides: Partial<typeof mockAnnotation> = {},
) {
  return { ...mockAnnotation, ...overrides };
}
