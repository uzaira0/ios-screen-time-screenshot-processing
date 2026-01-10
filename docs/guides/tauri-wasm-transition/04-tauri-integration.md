# Chapter 4: Tauri Integration

This chapter covers adding Tauri v2 to an existing React/Vite project, configuring plugins and capabilities, writing custom Rust commands, and managing the security boundary between web and native code.

---

## 1. Adding Tauri to an Existing React Project

### Initialization

From your frontend directory (the one containing `package.json` and `vite.config.ts`):

```bash
cd frontend
npx @tauri-apps/cli init
```

This scaffolds the Tauri structure inside your existing project:

```
frontend/
├── src/                      # existing React source
├── dist/                     # Vite build output
├── vite.config.ts
├── package.json
├── src-tauri/                # ← new
│   ├── Cargo.toml            # Rust dependencies
│   ├── tauri.conf.json       # Tauri configuration
│   ├── build.rs              # Build script (auto-generated)
│   ├── capabilities/
│   │   └── default.json      # Permission grants
│   ├── icons/                # App icons (all required sizes)
│   │   ├── 32x32.png
│   │   ├── 128x128.png
│   │   ├── 128x128@2x.png
│   │   ├── icon.ico
│   │   └── icon.png
│   └── src/
│       ├── main.rs           # Entry point (calls lib::run)
│       └── lib.rs            # Plugin init, commands, setup
```

### Key configuration in `tauri.conf.json`

```json
{
  "build": {
    "devUrl": "http://localhost:5173",
    "frontendDist": "../dist"
  }
}
```

- `devUrl` -- Tauri's webview loads this URL during `tauri dev`. Point it at your Vite dev server.
- `frontendDist` -- Relative path to the built frontend assets. Tauri embeds these into the binary during `tauri build`.

### Development workflow

```bash
# Terminal 1: Vite dev server
bun run dev

# Terminal 2: Tauri dev (opens native window pointing at Vite dev server)
npx @tauri-apps/cli dev
```

Tauri dev watches `src-tauri/src/` for Rust changes and recompiles automatically. Frontend HMR works through the webview as normal.

---

## 2. Plugin Architecture

Tauri v2 plugins follow a three-step pattern: Cargo dependency, Rust initialization, and capability grant.

### Step 1: Add the Cargo dependency

```toml
# frontend/src-tauri/Cargo.toml
[dependencies]
tauri = { version = "2", features = ["devtools"] }
tauri-plugin-dialog = "2"
tauri-plugin-fs = "2"
tauri-plugin-shell = "2"
tauri-plugin-updater = "2"
tauri-plugin-process = "2"
tauri-plugin-window-state = "2"
tauri-plugin-single-instance = "2"
tauri-plugin-store = "2"
tauri-plugin-log = "2"
tauri-plugin-notification = "2"
tauri-plugin-clipboard-manager = "2"
tauri-plugin-os = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

### Step 2: Initialize in Rust

Each plugin is registered via `.plugin()` on the Tauri builder:

```rust
// frontend/src-tauri/src/lib.rs
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_single_instance::init(|app, argv, cwd| {
            println!("{}, {argv:?}, {cwd}", app.package_info().name);
            let _ = app.emit("single-instance", SingleInstancePayload { args: argv, cwd });
        }))
        .plugin(
            tauri_plugin_log::Builder::new()
                .targets([
                    Target::new(TargetKind::Stdout),
                    Target::new(TargetKind::LogDir { file_name: None }),
                    Target::new(TargetKind::Webview),
                ])
                .build(),
        )
        .setup(|app| {
            #[cfg(desktop)]
            app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![select_screenshot_folder])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

Most plugins use a simple `::init()` function. Plugins with configuration (log, store, window-state) use a builder pattern. The updater is special -- it is initialized inside `.setup()` with `#[cfg(desktop)]` to exclude it from mobile builds.

### Step 3: Grant capabilities

Without a matching permission in `capabilities/default.json`, the JavaScript API for a plugin silently returns nothing or throws a permission error.

### Plugin catalog

| Plugin | Purpose | JS Package | Init Pattern |
|--------|---------|-----------|--------------|
| `dialog` | Native file/folder pickers, message boxes | `@tauri-apps/plugin-dialog` | `::init()` |
| `fs` | Read/write files on disk | `@tauri-apps/plugin-fs` | `::init()` |
| `shell` | Open URLs in default browser | `@tauri-apps/plugin-shell` | `::init()` |
| `updater` | In-app auto-updates | `@tauri-apps/plugin-updater` | Builder in `.setup()` |
| `process` | Restart/exit the app | `@tauri-apps/plugin-process` | `::init()` |
| `window-state` | Persist/restore window size and position | `@tauri-apps/plugin-window-state` | `Builder::default().build()` |
| `single-instance` | Prevent multiple app instances | (event-based) | `::init(callback)` |
| `store` | Persistent key-value store | `@tauri-apps/plugin-store` | `Builder::default().build()` |
| `log` | Multi-target logging (stdout, file, webview) | `@tauri-apps/plugin-log` | Builder with targets |
| `notification` | OS-native notifications | `@tauri-apps/plugin-notification` | `::init()` |
| `clipboard-manager` | System clipboard read/write | `@tauri-apps/plugin-clipboard-manager` | `::init()` |
| `os` | OS info (platform, version, arch) | `@tauri-apps/plugin-os` | `::init()` |

---

## 3. Capabilities

Tauri v2 uses a capabilities system that acts as a permission firewall between the webview (untrusted) and native APIs (privileged). Every plugin API call is gated by a capability grant.

### `capabilities/default.json`

```json
{
  "identifier": "default",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "shell:allow-open",
    "dialog:allow-open",
    "fs:allow-read-file",
    "updater:default",
    "process:allow-restart",
    "window-state:allow-restore-state",
    "window-state:allow-save-window-state",
    "window-state:allow-filename",
    "store:default",
    "notification:default",
    "clipboard-manager:allow-read-text",
    "clipboard-manager:allow-write-text",
    "os:default"
  ]
}
```

### Permission naming convention

```
<plugin>:<scope>

core:default              # Standard window management, IPC
shell:allow-open          # Allow opening URLs (not arbitrary shell commands)
fs:allow-read-file        # Allow reading files (but not writing or listing directories)
dialog:allow-open         # Allow file/folder open dialogs (but not save dialogs)
updater:default           # All updater operations (check, download, install)
process:allow-restart     # Allow app restart (but not exit or kill)
```

### Principle of least privilege

Grant only what the app needs:

- `fs:allow-read-file` instead of `fs:default` (which includes write and delete)
- `shell:allow-open` instead of `shell:default` (which includes `execute`)
- Separate read/write permissions for clipboard
- No `fs:allow-write-file` because blob storage uses OPFS/IndexedDB, not the native filesystem

### Window scoping

The `"windows": ["main"]` field restricts these permissions to the main window. If you add additional windows (e.g., a settings panel), they get no permissions by default. Create a separate capability file for each window that needs native access.

### Debugging permission issues

When a JS call to a Tauri plugin returns `undefined` or throws `"Not allowed"`:

1. Check the capability file for the matching permission string
2. Check the plugin name matches the Cargo dependency name
3. Check the window label matches `"windows"` in the capability
4. Check the Rust side has `.plugin(tauri_plugin_<name>::init())`

---

## 4. Custom Tauri Commands

Tauri commands bridge JavaScript and Rust. The `#[tauri::command]` macro generates the IPC serialization layer.

### Defining a command

```rust
use serde::Serialize;
use std::fs;
use std::path::Path;
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

#[derive(Serialize)]
pub struct SelectedFile {
    pub name: String,
    pub path: String,
}

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

fn scan_image_files(dir: &Path) -> Result<Vec<SelectedFile>, String> {
    let entries = fs::read_dir(dir).map_err(|e| format!("Failed to read directory: {e}"))?;

    let mut files = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|e| format!("Failed to read entry: {e}"))?;
        let path = entry.path();

        if !path.is_file() {
            continue;
        }

        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();

        if !matches!(ext.as_str(), "png" | "jpg" | "jpeg" | "heic" | "webp") {
            continue;
        }

        files.push(SelectedFile {
            name: path.file_name().and_then(|n| n.to_str()).unwrap_or("unknown").to_string(),
            path: path.to_string_lossy().to_string(),
        });
    }

    Ok(files)
}
```

### Registering the command

Commands must be registered in the invoke handler:

```rust
.invoke_handler(tauri::generate_handler![select_screenshot_folder])
```

Multiple commands are comma-separated:

```rust
.invoke_handler(tauri::generate_handler![
    select_screenshot_folder,
    get_app_version,
    process_image_native,
])
```

### Calling from JavaScript

```typescript
import { invoke } from "@tauri-apps/api/core";

interface SelectedFile {
  name: string;
  path: string;
}

const files = await invoke<SelectedFile[]>("select_screenshot_folder");
```

### Command design rules

1. **Return `Result<T, String>`.** Tauri serializes the `Err` variant as a JS error. Use `.map_err(|e| e.to_string())` to convert Rust errors.
2. **Use `async` for I/O.** Synchronous commands block the main thread. Even `fs::read_dir` should be in an `async` command (Tauri runs it on a thread pool).
3. **Accept `tauri::AppHandle` for plugin access.** The app handle provides access to dialog, window, and other plugin APIs.
4. **Derive `Serialize` on return types.** Tauri uses serde to convert Rust structs to JSON for the IPC bridge.
5. **Avoid returning raw bytes.** For large binary data (images), return a file path and let the frontend read it via `tauri-plugin-fs`, or write to a temp file.

---

## 5. CSP for Tauri

The Content Security Policy controls what the webview can load and execute. Tauri enforces CSP at the native level, not just via HTTP headers.

### Real CSP from `tauri.conf.json`

```json
{
  "app": {
    "security": {
      "csp": "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self' ipc: http://ipc.localhost http: https:; worker-src 'self' blob:; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com"
    }
  }
}
```

### Directive breakdown

| Directive | Value | Why |
|-----------|-------|-----|
| `default-src` | `'self'` | Baseline: only load from the app's own origin |
| `script-src` | `'self' 'wasm-unsafe-eval'` | Allow WASM execution (Tesseract.js). `'wasm-unsafe-eval'` is more restrictive than `'unsafe-eval'` -- it only allows `WebAssembly.compile()` |
| `connect-src` | `'self' ipc: http://ipc.localhost http: https:` | `ipc:` and `http://ipc.localhost` are Tauri's IPC channels. `http:` and `https:` allow fetching from APIs and the updater endpoint |
| `worker-src` | `'self' blob:` | Web Workers for Tesseract.js OCR. `blob:` is required because Tesseract creates workers from blob URLs |
| `img-src` | `'self' blob: data:` | `blob:` for OPFS-backed object URLs. `data:` for inline images (icons, SVGs) |
| `style-src` | `'self' 'unsafe-inline' https://fonts.googleapis.com` | `'unsafe-inline'` for CSS-in-JS (Tailwind, styled components). Google Fonts stylesheet |
| `font-src` | `'self' data: https://fonts.gstatic.com` | Google Fonts files. `data:` for embedded icon fonts |

### Common CSP mistakes

**Missing `ipc:` in `connect-src`:** All `invoke()` calls fail silently. The webview cannot reach the Rust backend.

**Missing `blob:` in `worker-src`:** Tesseract.js fails to initialize. The library creates a Web Worker from a blob URL generated at runtime.

**Restricting `connect-src` to specific HTTPS hosts:** The updater plugin fetches from GitHub, which redirects to `objects.githubusercontent.com`. Restricting to `https://github.com` breaks the download. Use `https:` to allow all HTTPS origins unless you control all endpoints.

**Missing `'wasm-unsafe-eval'` in `script-src`:** WASM instantiation fails. This affects Tesseract.js and any other WASM module. Note: `'unsafe-eval'` also works but is more permissive than needed.

---

## 6. Dynamic Imports

In a dual-mode application (web/WASM + Tauri), Tauri-specific packages (`@tauri-apps/*`) must not be statically imported in shared code. Static imports cause Vite to bundle them, and the build fails in web mode because the packages resolve to nothing.

### Pattern: dynamic import with runtime guard

```typescript
// shared code -- runs in web, WASM, and Tauri modes
import { config } from "../config";

export async function openInBrowser(url: string): Promise<void> {
  if (config.isTauri) {
    const { open } = await import("@tauri-apps/plugin-shell");
    await open(url);
  } else {
    window.open(url, "_blank");
  }
}
```

### Pattern: lazy module wrapper

For modules with multiple exports, create a thin wrapper that centralizes the dynamic import:

```typescript
// frontend/src/lib/updater.ts
export async function checkForUpdate(): Promise<UpdateInfo | null> {
  const { check } = await import("@tauri-apps/plugin-updater");
  const update = await check();
  // ...
}

export async function relaunchApp(): Promise<void> {
  const { relaunch } = await import("@tauri-apps/plugin-process");
  await relaunch();
}
```

The component guards on `config.isTauri` before calling any of these functions. The dynamic `import()` never executes in web mode.

### Vite configuration

No special Vite configuration is needed. Dynamic `import()` with string literal paths is handled by Vite's code splitting. In web builds, the `@tauri-apps/*` packages are excluded from the bundle entirely because no static import references them.

If you use `@tauri-apps/api` (the core API package) in shared code, add it to `build.rollupOptions.external` in `vite.config.ts` to avoid bundling errors:

```typescript
export default defineConfig({
  build: {
    rollupOptions: {
      external: config.isTauri ? [] : [/^@tauri-apps\//],
    },
  },
});
```

---

## 7. Mode-Specific Bootstrap

The DI container bootstraps different service implementations based on the runtime mode. Tauri mode starts as a thin wrapper around WASM services and evolves toward native implementations.

### Bootstrap entry point

```typescript
// frontend/src/core/di/bootstrapTauri.ts
import { bootstrapWasmServices } from "./bootstrapWasm";
import type { AppConfig } from "../config";
import type { ServiceContainer } from "./Container";

/**
 * Bootstrap services for Tauri (desktop) mode.
 *
 * Phase 1: Reuses WASM services (IndexedDB + Tesseract.js).
 * Phase 2+: Swap in TauriStorageService (SQLite), native file access, Rust OCR.
 */
export function bootstrapTauriServices(config: AppConfig): ServiceContainer {
  return bootstrapWasmServices(config);
}
```

### Evolution path

| Phase | Storage | OCR | File Access |
|-------|---------|-----|-------------|
| **1 (current)** | IndexedDB + OPFS (via WASM services) | Tesseract.js in Web Worker | `<input type="file">` + OPFS |
| **2** | SQLite via `tauri-plugin-sql` | Tesseract.js | Native file dialog via `tauri-plugin-dialog` |
| **3** | SQLite | Rust-native OCR (Tesseract C bindings or custom) | Direct `fs::read` via Tauri command |

Each phase requires only changing the service registration in `bootstrapTauriServices`. The rest of the app remains identical because components access services through the DI container, not direct imports.

### Mode detection

```typescript
// frontend/src/config.ts
export const config = {
  isTauri: "__TAURI_INTERNALS__" in window,
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL,
  // Server mode: apiBaseUrl is set
  // WASM mode: apiBaseUrl is undefined, isTauri is false
  // Tauri mode: apiBaseUrl is undefined, isTauri is true
};
```

The bootstrap dispatcher:

```typescript
// frontend/src/core/di/bootstrap.ts
import { config } from "../config";

export function bootstrap(): ServiceContainer {
  if (config.apiBaseUrl) {
    return bootstrapServerServices(config);
  } else if (config.isTauri) {
    return bootstrapTauriServices(config);
  } else {
    return bootstrapWasmServices(config);
  }
}
```

---

## 8. Window State Persistence

The `tauri-plugin-window-state` plugin saves and restores the window's position, size, and maximized/minimized state across app launches.

### Setup

```rust
// Rust
.plugin(tauri_plugin_window_state::Builder::default().build())
```

```json
// capabilities/default.json
"window-state:allow-restore-state",
"window-state:allow-save-window-state",
"window-state:allow-filename"
```

### Behavior

- On window close: size, position, and maximized state are saved to a platform-specific config directory
- On app launch: the saved state is restored automatically
- No frontend code is needed -- the plugin hooks into window lifecycle events

### Configuration

The default builder persists all state. To customize:

```rust
use tauri_plugin_window_state::StateFlags;

.plugin(
    tauri_plugin_window_state::Builder::default()
        .with_state_flags(StateFlags::SIZE | StateFlags::POSITION)  // skip maximize state
        .build()
)
```

---

## 9. Single Instance

The `tauri-plugin-single-instance` plugin prevents users from opening multiple copies of the app. When a second instance is launched, it sends its arguments to the first instance and exits.

### Setup

```rust
use tauri::Emitter;

#[derive(Clone, serde::Serialize)]
struct SingleInstancePayload {
    args: Vec<String>,
    cwd: String,
}

.plugin(tauri_plugin_single_instance::init(|app, argv, cwd| {
    println!("{}, {argv:?}, {cwd}", app.package_info().name);
    let _ = app.emit("single-instance", SingleInstancePayload { args: argv, cwd });
}))
```

### Frontend handling

Listen for the event to handle files dropped on the app icon or command-line arguments:

```typescript
import { listen } from "@tauri-apps/api/event";

listen("single-instance", (event) => {
  const { args, cwd } = event.payload as { args: string[]; cwd: string };
  // Focus the existing window, process args, etc.
});
```

### Platform behavior

| Platform | Mechanism |
|----------|-----------|
| macOS | Uses `NSDistributedNotificationCenter` to detect running instances |
| Windows | Uses a named mutex |
| Linux | Uses a Unix domain socket |

---

## 10. Build Configuration

### `tauri.conf.json` build settings

```json
{
  "productName": "iOS Screen Time",
  "version": "0.3.42",
  "identifier": "com.ios-screentime.desktop",
  "app": {
    "windows": [
      {
        "title": "iOS Screen Time",
        "width": 1400,
        "height": 900
      }
    ]
  },
  "bundle": {
    "active": true,
    "createUpdaterArtifacts": true,
    "targets": ["app", "dmg", "nsis", "msi", "deb", "appimage"],
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.png",
      "icons/icon.ico"
    ]
  }
}
```

### Bundle targets

| Target | Platform | Output | Purpose |
|--------|----------|--------|---------|
| `app` | macOS | `.app` bundle | The actual application |
| `dmg` | macOS | `.dmg` disk image | Drag-to-install distribution |
| `nsis` | Windows | `_setup.exe` | Installer with desktop shortcut, uninstaller |
| `msi` | Windows | `.msi` | Enterprise/GPO deployment |
| `deb` | Linux | `.deb` package | Debian/Ubuntu package manager install |
| `appimage` | Linux | `.AppImage` | Portable, no-install binary |

### Version management

The version must be kept in sync between two files:

| File | Field | Example |
|------|-------|---------|
| `frontend/src-tauri/tauri.conf.json` | `"version"` | `"0.3.42"` |
| `frontend/src-tauri/Cargo.toml` | `version` | `"0.3.16"` |

The `tauri.conf.json` version is used by the updater plugin to determine the current version displayed to users and compared against `latest.json`. The `Cargo.toml` version is used by Cargo for the Rust binary. In practice, keeping them in sync avoids confusion, though only `tauri.conf.json` matters for the update mechanism.

### Icons

Tauri requires specific icon sizes for each platform:

- **macOS:** 128x128, 128x128@2x (256x256), 32x32
- **Windows:** `.ico` file (multi-resolution)
- **Linux:** `icon.png` (256x256 recommended)

Generate all sizes from a single high-resolution source:

```bash
npx @tauri-apps/cli icon path/to/1024x1024.png
```

### Build command

```bash
# Development (connects to Vite dev server)
npx @tauri-apps/cli dev

# Production build (embeds frontend assets)
npx @tauri-apps/cli build

# macOS universal binary (both Intel and Apple Silicon)
npx @tauri-apps/cli build --target universal-apple-darwin
```

The production build:

1. Runs `vite build` to produce `dist/`
2. Compiles the Rust binary with embedded frontend assets
3. Generates installers and updater artifacts based on `bundle.targets`
4. If `TAURI_SIGNING_PRIVATE_KEY` is set, signs updater artifacts with minisign
