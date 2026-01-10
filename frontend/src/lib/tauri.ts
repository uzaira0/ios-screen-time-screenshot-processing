/**
 * Tauri-specific utilities.
 * All imports from @tauri-apps/* are dynamic to avoid breaking web builds.
 */

export interface SelectedFile {
  name: string;
  path: string;
}

export async function selectScreenshotFolder(): Promise<SelectedFile[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { invoke } = (await import("@tauri-apps/api/core")) as any;
  return invoke("select_screenshot_folder") as Promise<SelectedFile[]>;
}

export async function readImageFile(path: string): Promise<Uint8Array> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { readFile } = (await import("@tauri-apps/plugin-fs")) as any;
  return readFile(path) as Promise<Uint8Array>;
}
