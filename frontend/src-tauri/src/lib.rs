use ios_screen_time_image_pipeline as processing;

use serde::Serialize;
use std::fs;
use std::path::Path;
use tauri::Emitter;
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_log::{Target, TargetKind};

use processing::types::{DetectionMethod, ImageType};

#[derive(Clone, serde::Serialize)]
struct SingleInstancePayload {
    args: Vec<String>,
    cwd: String,
}

#[derive(Serialize)]
pub struct SelectedFile {
    pub name: String,
    pub path: String,
}

/// Opens a native folder picker and returns metadata for image files found.
/// File bytes are NOT loaded here — the frontend reads them lazily via tauri-plugin-fs.
#[tauri::command]
async fn select_screenshot_folder(app: tauri::AppHandle) -> Result<Vec<SelectedFile>, String> {
    let folder = app
        .dialog()
        .file()
        .set_title("Select Screenshot Folder")
        .blocking_pick_folder();

    let folder = match folder {
        Some(f) => f.into_path().map_err(|e| e.to_string())?,
        None => return Ok(vec![]),
    };

    scan_image_files(&folder)
}

/// Process a screenshot with automatic grid detection.
///
/// Returns hourly values, grid bounds, alignment score, and OCR results.
#[tauri::command]
async fn process_screenshot(
    path: String,
    image_type: String,
    detection_method: String,
) -> Result<processing::ProcessingResult, String> {
    let img_type = ImageType::from_str(&image_type);
    let method = DetectionMethod::from_str(&detection_method);

    processing::process_image(&path, img_type, method).map_err(|e| e.to_string())
}

/// Process a screenshot with user-provided grid coordinates.
#[tauri::command]
async fn process_screenshot_with_grid(
    path: String,
    upper_left: [i32; 2],
    lower_right: [i32; 2],
    image_type: String,
) -> Result<processing::ProcessingResult, String> {
    let img_type = ImageType::from_str(&image_type);

    processing::process_image_with_grid(&path, upper_left, lower_right, img_type)
        .map_err(|e| e.to_string())
}

/// Extract only hourly data (fast path — no OCR, no grid detection).
#[tauri::command]
async fn extract_hourly_data(
    path: String,
    upper_left: [i32; 2],
    lower_right: [i32; 2],
    image_type: String,
) -> Result<Vec<f64>, String> {
    let img_type = ImageType::from_str(&image_type);

    processing::extract_hourly_data(&path, upper_left, lower_right, img_type)
        .map_err(|e| e.to_string())
}

/// Check if an extension (as OsStr) matches a known image extension,
/// handling case-insensitive comparison without allocating.
fn is_image_extension(ext: &std::ffi::OsStr) -> bool {
    // Fast path: try as ASCII bytes directly to avoid allocation
    let bytes = ext.as_encoded_bytes();
    if bytes.len() > 4 {
        return false;
    }
    // Lowercase the bytes in-place on the stack
    let mut buf = [0u8; 4];
    let len = bytes.len();
    for (i, &b) in bytes.iter().enumerate() {
        buf[i] = b.to_ascii_lowercase();
    }
    let lower = &buf[..len];
    matches!(lower, b"png" | b"jpg" | b"jpeg" | b"heic" | b"webp")
}

fn scan_image_files(dir: &Path) -> Result<Vec<SelectedFile>, String> {
    let entries = fs::read_dir(dir).map_err(|e| format!("Failed to read directory: {e}"))?;

    // Pre-allocate with a reasonable capacity hint to reduce reallocations
    let mut files = Vec::with_capacity(entries.size_hint().0.max(64));

    for entry in entries {
        let entry = entry.map_err(|e| format!("Failed to read entry: {e}"))?;

        // Use entry.file_type() instead of path.is_file() to avoid an extra stat syscall.
        // read_dir already has the file type from the directory entry (d_type on Unix).
        let ft = entry
            .file_type()
            .map_err(|e| format!("Failed to read file type: {e}"))?;
        if !ft.is_file() {
            continue;
        }

        // Check extension using OsStr comparison — no heap allocation for lowercase
        let path = entry.path();
        match path.extension() {
            Some(ext) if is_image_extension(ext) => {}
            _ => continue,
        }

        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown")
            .to_string();

        let path_str = path.to_string_lossy().into_owned();

        files.push(SelectedFile {
            name,
            path: path_str,
        });
    }

    Ok(files)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_single_instance::init(|app, argv, cwd| {
            println!("{}, {argv:?}, {cwd}", app.package_info().name);
            let _ = app.emit("single-instance", SingleInstancePayload { args: argv, cwd });
        }))
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(
            tauri_plugin_log::Builder::new()
                .targets([
                    Target::new(TargetKind::Stdout),
                    Target::new(TargetKind::LogDir { file_name: None }),
                    Target::new(TargetKind::Webview),
                ])
                .build(),
        )
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_os::init())
        .setup(|app| {
            #[cfg(desktop)]
            app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            select_screenshot_folder,
            process_screenshot,
            process_screenshot_with_grid,
            extract_hourly_data,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;
    use tempfile::TempDir;

    #[test]
    fn test_scan_image_files_finds_images() {
        let dir = TempDir::new().unwrap();

        // Create test image files
        fs::write(dir.path().join("photo.png"), b"fake png").unwrap();
        fs::write(dir.path().join("photo.jpg"), b"fake jpg").unwrap();
        fs::write(dir.path().join("photo.jpeg"), b"fake jpeg").unwrap();
        fs::write(dir.path().join("photo.webp"), b"fake webp").unwrap();
        fs::write(dir.path().join("photo.heic"), b"fake heic").unwrap();

        let result = scan_image_files(dir.path()).unwrap();
        assert_eq!(result.len(), 5, "Should find all 5 image files");
    }

    #[test]
    fn test_scan_image_files_ignores_non_images() {
        let dir = TempDir::new().unwrap();

        fs::write(dir.path().join("document.pdf"), b"fake pdf").unwrap();
        fs::write(dir.path().join("readme.txt"), b"text").unwrap();
        fs::write(dir.path().join("data.json"), b"{}").unwrap();
        fs::write(dir.path().join("photo.png"), b"fake png").unwrap();

        let result = scan_image_files(dir.path()).unwrap();
        assert_eq!(result.len(), 1, "Should only find the PNG");
        assert_eq!(result[0].name, "photo.png");
    }

    #[test]
    fn test_scan_image_files_empty_directory() {
        let dir = TempDir::new().unwrap();
        let result = scan_image_files(dir.path()).unwrap();
        assert!(result.is_empty(), "Empty directory should return no files");
    }

    #[test]
    fn test_scan_image_files_skips_directories() {
        let dir = TempDir::new().unwrap();
        fs::create_dir(dir.path().join("subdir")).unwrap();
        fs::write(dir.path().join("photo.png"), b"fake png").unwrap();

        let result = scan_image_files(dir.path()).unwrap();
        assert_eq!(result.len(), 1, "Should skip subdirectories");
    }

    #[test]
    fn test_scan_image_files_case_insensitive_extension() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("PHOTO.PNG"), b"fake").unwrap();
        fs::write(dir.path().join("Image.JPG"), b"fake").unwrap();

        let result = scan_image_files(dir.path()).unwrap();
        assert_eq!(result.len(), 2, "Should handle uppercase extensions");
    }

    #[test]
    fn test_selected_file_has_correct_fields() {
        let dir = TempDir::new().unwrap();
        let img_path = dir.path().join("test-screenshot.png");
        fs::write(&img_path, b"fake png").unwrap();

        let result = scan_image_files(dir.path()).unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].name, "test-screenshot.png");
        assert!(result[0].path.ends_with("test-screenshot.png"));
    }

    #[test]
    fn test_scan_nonexistent_directory() {
        let result = scan_image_files(&PathBuf::from("/nonexistent/path"));
        assert!(result.is_err(), "Should return error for nonexistent directory");
    }
}
