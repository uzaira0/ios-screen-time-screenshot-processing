# Chapter 5: Auto-Updates

This chapter covers in-app auto-updates using Tauri v2's updater plugin, minisign code signing, GitHub Releases as the distribution channel, and the CI/CD pipeline that ties it all together.

---

## 1. Architecture Overview

```
┌─────────────────┐    check()      ┌───────────────────┐    fetch     ┌──────────────────┐
│  UpdateBanner    │ ──────────────► │ tauri-plugin-      │ ──────────► │ GitHub Releases   │
│  (React)         │                 │ updater (Rust)     │             │ latest.json       │
└────────┬────────┘                 └─────────┬─────────┘             └──────────────────┘
         │                                    │
         │  downloadAndInstall()              │ download + verify signature
         │◄───────────────────────────────────┘
         │
         │  relaunch()
         ▼
┌─────────────────┐
│ tauri-plugin-    │
│ process          │ ── app restarts with new version
└─────────────────┘
```

**Update flow:**

1. App starts. `UpdateBanner` waits 3 seconds, then calls `checkForUpdate()`.
2. The updater plugin fetches `latest.json` from the GitHub Releases endpoint.
3. It compares the `latest.json` version against the current app version (from `tauri.conf.json`).
4. If newer: user sees a banner with the new version number and optional release notes.
5. User clicks "Update now". The plugin downloads the platform-specific artifact.
6. The plugin verifies the `.sig` signature against the public key embedded in the app.
7. It installs to a temp location. The banner changes to "Restart to apply."
8. User clicks "Restart." The app relaunches with the new version.

**Periodic re-checks:** After the initial check, the banner re-checks every 15 minutes and when the app regains focus (with a 60-second cooldown to avoid rapid re-checks from visibility/focus firing together).

---

## 2. Key Generation

The updater uses [minisign](https://jedisct1.github.io/minisign/) signatures. Generate a keypair once per project.

```bash
cd frontend
npx @tauri-apps/cli signer generate
```

This outputs three values:

| Value | Where it goes | Committed to repo? |
|-------|--------------|-------------------|
| **Public key** (base64) | `tauri.conf.json` `plugins.updater.pubkey` | Yes |
| **Private key** (base64) | GitHub repo secret `TAURI_SIGNING_PRIVATE_KEY` | No |
| **Password** (optional) | GitHub repo secret `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | No |

Store the private key and password immediately. You cannot regenerate the same keypair.

### GitHub secrets setup

Navigate to your repository's **Settings > Secrets and variables > Actions** and add:

| Secret Name | Value |
|-------------|-------|
| `TAURI_SIGNING_PRIVATE_KEY` | The full private key string |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | The password (or empty string if none) |

These secrets are read by the CI workflow during `npx @tauri-apps/cli build`. The Tauri CLI detects them in the environment and signs all updater artifacts automatically.

---

## 3. Tauri Configuration

### `plugins.updater` in `tauri.conf.json`

```json
{
  "version": "0.3.42",
  "plugins": {
    "updater": {
      "pubkey": "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDhGODdCNDc5NTkwQzAxMjUKUldRbEFReFplYlNIajlaaFhBY3pScjNtNmtHZWMxS2thNDdUWDRLc3lFSzVzOGo0MFVwb1BOSGsK",
      "endpoints": [
        "https://github.com/OWNER/REPO/releases/latest/download/latest.json"
      ]
    }
  },
  "bundle": {
    "active": true,
    "createUpdaterArtifacts": true,
    "targets": ["app", "dmg", "nsis", "msi", "deb", "appimage"]
  }
}
```

### Field reference

| Field | Purpose |
|-------|---------|
| `pubkey` | Base64-encoded minisign public key. Embedded in the binary at build time. Used to verify downloaded artifacts at runtime. |
| `endpoints` | Array of URLs to check for `latest.json`. Tried in order; first successful response wins. |
| `createUpdaterArtifacts` | When `true`, the Tauri build produces `.sig` signature files alongside each updater artifact. |

### Endpoint URL

The URL uses GitHub's `/releases/latest/download/` path, which redirects to the most recent non-prerelease release. This means:

- Stable users always see the latest stable version
- Prerelease tags (containing `-`, e.g., `v0.4.0-beta.1`) are automatically excluded
- No server infrastructure needed -- GitHub serves the static JSON file

### Rust dependencies

```toml
# frontend/src-tauri/Cargo.toml
[dependencies]
tauri-plugin-updater = "2"    # the updater itself
tauri-plugin-process = "2"    # for relaunch() after install
```

### Rust initialization

The updater plugin is initialized inside `.setup()` with `#[cfg(desktop)]` to exclude it from mobile builds:

```rust
// frontend/src-tauri/src/lib.rs
.plugin(tauri_plugin_process::init())
// ...
.setup(|app| {
    #[cfg(desktop)]
    app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;
    Ok(())
})
```

Why `.setup()` instead of `.plugin()`? The updater plugin's builder requires an `AppHandle`, which is only available after the app is initialized. The `#[cfg(desktop)]` attribute avoids compile errors on mobile targets.

### Capabilities

```json
{
  "identifier": "default",
  "windows": ["main"],
  "permissions": [
    "updater:default",
    "process:allow-restart"
  ]
}
```

Without `updater:default`, the JS `check()` call silently returns nothing. Without `process:allow-restart`, `relaunch()` throws a permission error.

### CSP

The updater needs to reach GitHub over HTTPS. The `connect-src` directive must include `https:`:

```
connect-src 'self' ipc: http://ipc.localhost http: https:
```

Do not restrict this to `https://github.com`. GitHub redirects artifact downloads to `objects.githubusercontent.com`, so a restrictive allowlist breaks the download phase.

---

## 4. Frontend Update Library

A thin wrapper around the Tauri updater JS plugin. All `@tauri-apps/*` imports are dynamic to avoid breaking web/WASM builds where these packages do not exist.

```typescript
// frontend/src/lib/updater.ts

export interface UpdateInfo {
  version: string;
  currentVersion: string;
  body?: string;
  date?: string;
}

export interface UpdateProgress {
  downloaded: number;   // bytes in this chunk (not cumulative)
  total: number;        // total bytes (0 if unknown)
}

// Module-level state: holds the Update object between check and install
let pendingUpdate: {
  available?: boolean;
  version: string;
  currentVersion: string;
  body?: string;
  date?: string;
  downloadAndInstall: (cb: (event: UpdateEvent) => void) => Promise<void>;
} | null = null;

interface UpdateEvent {
  event: "Started" | "Progress" | "Finished";
  data: { contentLength?: number; chunkLength?: number };
}

export async function checkForUpdate(): Promise<UpdateInfo | null> {
  const { check } = await import("@tauri-apps/plugin-updater");
  const update = await check();

  if (!update?.available) {
    pendingUpdate = null;
    return null;
  }

  pendingUpdate = update;

  return {
    version: update.version,
    currentVersion: update.currentVersion,
    body: update.body ?? undefined,
    date: update.date ?? undefined,
  };
}

export async function downloadAndInstall(
  onProgress?: (progress: UpdateProgress) => void,
): Promise<void> {
  if (!pendingUpdate) {
    throw new Error("No pending update. Call checkForUpdate() first.");
  }

  let totalBytes = 0;

  await pendingUpdate.downloadAndInstall((event: UpdateEvent) => {
    if (!onProgress) return;

    switch (event.event) {
      case "Started":
        totalBytes = event.data.contentLength ?? 0;
        onProgress({ downloaded: 0, total: totalBytes });
        break;
      case "Progress":
        onProgress({ downloaded: event.data.chunkLength ?? 0, total: totalBytes });
        break;
      case "Finished":
        onProgress({ downloaded: totalBytes, total: totalBytes });
        break;
    }
  });
}

export async function relaunchApp(): Promise<void> {
  const { relaunch } = await import("@tauri-apps/plugin-process");
  await relaunch();
}
```

### Why `pendingUpdate` is module-level state

The `check()` API returns an `Update` object with a `.downloadAndInstall()` method bound to the specific update. You cannot call `check()` again and get the same object -- each call makes a new network request. The module stashes the object so the UI can display the "update available" state and the user can click "Install" without triggering another check.

### Why dynamic imports

This file is bundled into both the Tauri desktop build and the web/WASM build. In web mode, `@tauri-apps/plugin-updater` does not exist. Dynamic `import()` defers resolution to runtime. The `UpdateBanner` component guards on `config.isTauri` before calling any of these functions, so the import never executes in web mode and the build does not fail.

---

## 5. UpdateBanner Component

The banner is a state machine that manages the full update lifecycle.

### State types

```typescript
type BannerState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "available"; info: UpdateInfo }
  | { status: "downloading"; percent: number | null; downloaded: number; total: number }
  | { status: "ready"; info: UpdateInfo }
  | { status: "error"; message: string; retryAction?: "check" | "download"; info?: UpdateInfo }
  | { status: "dismissed"; version: string };
```

### State machine transitions

```
                    ┌──────────────────────────────────────────────────┐
                    │                                                  │
                    ▼                                                  │
 ┌──────┐    ┌──────────┐    ┌───────────┐    ┌─────────────┐    ┌───────┐
 │ idle │───►│ checking │───►│ available │───►│ downloading │───►│ ready │
 └──────┘    └──────────┘    └───────────┘    └─────────────┘    └───────┘
                  │               │                │                 │
                  │               │                │                 │
                  ▼               ▼                ▼                 ▼
             ┌────────┐    ┌───────────┐    ┌────────┐         (relaunch)
             │  idle  │    │ dismissed │    │ error  │
             │(no upd)│    │(user X'd) │    │(retry) │
             └────────┘    └───────────┘    └────────┘
                                                │
                                          ┌─────┴─────┐
                                          ▼           ▼
                                       checking   downloading
                                      (retry=     (retry=
                                       check)      download)
```

### Key behaviors

**Initial delay:** The check fires 3 seconds after mount, not immediately. This avoids blocking app startup.

**Periodic re-checks:** An interval timer re-checks every 15 minutes:

```typescript
intervalRef.current = setInterval(doCheck, CHECK_INTERVAL_MS);
```

**Visibility/focus re-check:** When the app returns to the foreground (e.g., user switches back from another window), a re-check fires if at least 60 seconds have passed since the last check:

```typescript
const handleAppResume = () => {
  if (document.visibilityState !== "visible") return;
  if (Date.now() - lastCheckRef.current < VISIBILITY_COOLDOWN_MS) return;
  doCheck();
};
document.addEventListener("visibilitychange", handleAppResume);
window.addEventListener("focus", handleAppResume);
```

Both `visibilitychange` and `focus` can fire on the same user action. The `checkInFlightRef` guard prevents concurrent checks.

**Exponential backoff retry:** Failed checks retry up to 3 times with exponential backoff (5s, 10s, 20s):

```typescript
if (retryCount.current < MAX_RETRIES) {
  retryCount.current++;
  const delay = RETRY_BASE_MS * Math.pow(2, retryCount.current - 1);
  setTimeout(doCheck, delay);
  return;
}
```

**Dismiss per version:** When the user dismisses the banner, it records the dismissed version. If a newer version is found on the next check, the banner reappears:

```typescript
setState((prev) => {
  if (prev.status === "dismissed" && prev.version === info.version) {
    return prev;  // same version, stay dismissed
  }
  return { status: "available", info };  // new version, show banner
});
```

**Download progress:** The `onProgress` callback receives per-chunk bytes (not cumulative). The component accumulates `downloadedSoFar` to compute the percentage:

```typescript
let downloadedSoFar = 0;
await downloadAndInstall((progress) => {
  downloadedSoFar += progress.downloaded;
  const percent = Math.min(100, Math.round((downloadedSoFar / progress.total) * 100));
  setState({ status: "downloading", percent, downloaded: downloadedSoFar, total: progress.total });
});
```

**Error recovery:** The error state tracks whether the failure occurred during check or download, so the retry button invokes the correct action:

```typescript
const handleRetry = () => {
  if (state.retryAction === "download") {
    handleUpdate();
  } else {
    doCheck();
  }
};
```

### Rendering

The banner renders nothing for `idle`, `checking`, and `dismissed` states:

```typescript
if (!config.isTauri || state.status === "idle" || state.status === "checking" || state.status === "dismissed") {
  return null;
}
```

Mount it at the top of your app layout so it appears above all content:

```tsx
<UpdateBanner />
<main>{children}</main>
```

---

## 6. CI/CD Workflow

The GitHub Actions workflow builds, signs, and publishes Tauri artifacts for all three platforms in a single pipeline.

### Trigger

```yaml
on:
  push:
    tags: ['tauri-v*']       # push a tag like tauri-v0.3.42
  workflow_dispatch:           # or trigger manually from Actions tab
    inputs:
      prerelease:
        description: 'Mark as prerelease'
        type: boolean
        default: false
```

### Build matrix

Builds run in parallel on 3 OS runners:

```yaml
strategy:
  fail-fast: false
  matrix:
    include:
      - os: macos-latest
        target: universal-apple-darwin
      - os: windows-latest
        target: x86_64-pc-windows-msvc
      - os: ubuntu-22.04
        target: x86_64-unknown-linux-gnu
```

`fail-fast: false` ensures a failure on one platform does not cancel the others.

### Build steps (per platform)

1. **Checkout** code
2. **Setup Node.js** (v22) and **Bun** (latest)
3. **Setup Rust** stable toolchain (macOS adds both `aarch64-apple-darwin` and `x86_64-apple-darwin` targets for universal binary)
4. **Rust cache** via `swatinem/rust-cache` (workspace path: `frontend/src-tauri -> target`)
5. **Linux deps** (Ubuntu only): `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf`
6. **Install frontend deps**: `bun install --frozen-lockfile`
7. **Build frontend**: `bun run --bun vite build`
8. **Validate updater config**: Checks that the pubkey is not a placeholder
9. **Clean old bundle artifacts**: Removes stale `release/bundle` directories to prevent artifact confusion
10. **Build Tauri**: `npx @tauri-apps/cli build` with signing environment variables
11. **Upload artifacts**: Updater artifacts (`.tar.gz`, `.sig`) and installer artifacts (`.dmg`, `.exe`, `.msi`, `.deb`, `.AppImage`) are uploaded separately

### Signing

Signing happens automatically during `npx @tauri-apps/cli build` when these environment variables are set:

```yaml
env:
  TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
  TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}
```

For each updater artifact, the build produces a `.sig` file containing the minisign signature.

### Release job

After all platform builds complete, the `release` job:

1. **Downloads all artifacts** from the build matrix
2. **Determines version and tag** from git ref or `tauri.conf.json`
3. **Creates tag** (for `workflow_dispatch` runs only)
4. **Flattens artifacts** from nested directories into a single `release-assets/` folder
5. **Generates `latest.json`** (see next section)
6. **Creates GitHub Release** with all assets using `softprops/action-gh-release`

### Annotated release job steps

```yaml
release:
  needs: build
  runs-on: ubuntu-latest
  permissions:
    contents: write    # needed to create releases and tags

  steps:
    - uses: actions/checkout@v4

    - name: Download all artifacts
      uses: actions/download-artifact@v4
      with:
        path: artifacts

    - name: Determine version and tag
      id: version
      run: |
        if [[ "$REF_TYPE" == "tag" ]]; then
          TAG="$REF_NAME"
          VERSION="${TAG#tauri-v}"        # strip prefix: tauri-v0.3.42 -> 0.3.42
        else
          VERSION=$(jq -r '.version' frontend/src-tauri/tauri.conf.json)
          TAG="tauri-v${VERSION}"
        fi

        # Detect prerelease: version contains '-' OR workflow_dispatch input
        PRERELEASE="false"
        if [[ "$VERSION" == *-* ]]; then
          PRERELEASE="true"
        fi

    - name: Flatten artifacts
      run: |
        mkdir -p release-assets
        find artifacts -type f \( \
          -name '*.tar.gz' -o -name '*.sig' \
          -o -name '*.dmg' -o -name '*.exe' -o -name '*.msi' \
          -o -name '*.deb' -o -name '*.AppImage' \
        \) -exec cp {} release-assets/ \;
```

---

## 7. `latest.json` Generation

The `latest.json` file is the contract between the updater plugin and the release server. It tells the plugin what version is available, where to download it, and the signature to verify.

### Format

```json
{
  "version": "v0.3.42",
  "notes": "Release v0.3.42",
  "pub_date": "2026-03-15T08:33:00Z",
  "platforms": {
    "darwin-universal": {
      "signature": "dW50cnVzdGVkIGNvbW1lbnQ...",
      "url": "https://github.com/OWNER/REPO/releases/download/tauri-v0.3.42/iOS.Screen.Time.app.tar.gz"
    },
    "darwin-aarch64": {
      "signature": "dW50cnVzdGVkIGNvbW1lbnQ...",
      "url": "https://github.com/OWNER/REPO/releases/download/tauri-v0.3.42/iOS.Screen.Time.app.tar.gz"
    },
    "darwin-x86_64": {
      "signature": "dW50cnVzdGVkIGNvbW1lbnQ...",
      "url": "https://github.com/OWNER/REPO/releases/download/tauri-v0.3.42/iOS.Screen.Time.app.tar.gz"
    },
    "windows-x86_64": {
      "signature": "dW50cnVzdGVkIGNvbW1lbnQ...",
      "url": "https://github.com/OWNER/REPO/releases/download/tauri-v0.3.42/iOS-Screen-Time_0.3.42_x64-setup.exe"
    },
    "linux-x86_64": {
      "signature": "dW50cnVzdGVkIGNvbW1lbnQ...",
      "url": "https://github.com/OWNER/REPO/releases/download/tauri-v0.3.42/iOS-Screen-Time_0.3.42_amd64.AppImage"
    }
  }
}
```

### Generation script

The shell script in the CI workflow discovers artifacts by file extension and reads their `.sig` files:

```bash
cd release-assets

# GitHub replaces spaces with dots in release asset filenames
sanitize() { echo "$1" | sed 's/ /./g'; }

# --- macOS ---
MAC_TARBALL=$(ls *.app.tar.gz 2>/dev/null | head -1 || true)
MAC_SIG=""
if [[ -n "$MAC_TARBALL" && -f "${MAC_TARBALL}.sig" ]]; then
  MAC_SIG=$(cat "${MAC_TARBALL}.sig")
fi

# --- Windows (NSIS exe) ---
WIN_EXE=$(ls *-setup.exe 2>/dev/null | grep -v '.sig$' | head -1 || true)
WIN_SIG=""
if [[ -n "$WIN_EXE" && -f "${WIN_EXE}.sig" ]]; then
  WIN_SIG=$(cat "${WIN_EXE}.sig")
fi

# --- Linux (AppImage) ---
LINUX_APPIMAGE=$(ls *.AppImage 2>/dev/null | grep -v '.sig$' | head -1 || true)
LINUX_SIG=""
if [[ -n "$LINUX_APPIMAGE" && -f "${LINUX_APPIMAGE}.sig" ]]; then
  LINUX_SIG=$(cat "${LINUX_APPIMAGE}.sig")
fi
```

Platforms are added dynamically. If a platform build failed (no artifact + signature), it is excluded from `latest.json`. If all platforms failed, the job exits with an error.

### macOS universal binary mapping

The macOS universal binary is mapped to three platform keys: `darwin-universal`, `darwin-aarch64`, and `darwin-x86_64`. All three point to the same `.app.tar.gz` URL. This ensures the updater finds a match regardless of the Mac's architecture.

### Filename sanitization

GitHub Releases replaces spaces in filenames with dots. If your product name is "iOS Screen Time", the `.app.tar.gz` file becomes `iOS.Screen.Time.app.tar.gz` in the download URL. The `sanitize()` function handles this.

---

## 8. Platform-Specific Formats

Tauri v2 uses different artifact formats per platform for the updater:

| Platform | Updater Artifact | Installer Artifact | Why Different? |
|----------|------------------|--------------------|----------------|
| macOS | `.app.tar.gz` | `.dmg` | The `.dmg` is a disk image for drag-to-install. The updater needs a plain `.app` bundle in a tarball it can extract and replace. |
| Windows | `-setup.exe` (NSIS) | `.exe`, `.msi` | The NSIS installer handles in-place upgrades (finds existing install, overwrites). Tauri v2 uses the `.exe` directly. (Tauri v1 used `.nsis.zip` -- this changed in v2.) |
| Linux | `.AppImage` | `.deb`, `.AppImage` | AppImage is self-contained and can be replaced atomically. The `.deb` is for package manager installs and does not support auto-update. |

The `createUpdaterArtifacts: true` flag tells the build to produce these updater-format artifacts alongside the regular installers, plus `.sig` signature files for each.

---

## 9. Signature Verification

### Flow

```
Build time (CI):                        Runtime (app):
┌──────────────────┐                    ┌──────────────────┐
│ tauri build       │   PRIVATE KEY     │ App checks       │   PUBLIC KEY
│ produces          │ ──────────────►   │ latest.json      │ ──────────────►
│ .app.tar.gz       │   signs → .sig   │ downloads        │   verifies .sig
│                   │                   │ artifact         │   against pubkey
└──────────────────┘                    └──────────────────┘   in tauri.conf.json
```

### Step by step

1. During CI build, `tauri build` reads `TAURI_SIGNING_PRIVATE_KEY` from the environment.
2. For each updater artifact (`.app.tar.gz`, `-setup.exe`, `.AppImage`), it produces a `.sig` file containing a minisign signature.
3. The CI workflow reads each `.sig` file and embeds its content as the `signature` field in `latest.json`.
4. At runtime, after downloading the artifact, the updater plugin computes the artifact's minisign signature and compares it against the `signature` from `latest.json`, using the `pubkey` from `tauri.conf.json`.
5. If verification fails, the update is rejected. This protects against tampered downloads, CDN compromises, and man-in-the-middle attacks.

### Key rotation

There is no automatic key rotation protocol. The public key is baked into each installed app binary. If you lose your private key:

1. Generate a new keypair
2. Update `tauri.conf.json` with the new public key
3. Update GitHub secrets with the new private key
4. Release a version signed with the **old** key that contains the **new** public key (if you still have the old key)
5. If the old key is lost, users must manually download and install the new version

---

## 10. Release Workflow

### Version bump and release

```bash
# 1. Bump version in BOTH files (must match for consistency)
#    - frontend/src-tauri/tauri.conf.json → "version": "X.Y.Z"
#    - frontend/src-tauri/Cargo.toml     → version = "X.Y.Z"

# 2. Commit
git add frontend/src-tauri/tauri.conf.json frontend/src-tauri/Cargo.toml
git commit -m "chore: bump Tauri version to X.Y.Z"

# 3. Tag and push (triggers CI)
git tag tauri-vX.Y.Z
git push origin main tauri-vX.Y.Z

# 4. Monitor the build (~7 minutes for all 3 platforms)
gh run watch

# 5. After completion, the release appears at:
#    https://github.com/OWNER/REPO/releases/tag/tauri-vX.Y.Z
#    Users' apps will see the update banner on next check.
```

### Alternative: manual trigger

Go to **Actions > Tauri Build > Run workflow**. This reads the version from `tauri.conf.json` and creates the tag automatically. Use the `prerelease` checkbox to mark it as a prerelease.

---

## 11. Prerelease Handling

### Automatic prerelease detection

Tags containing `-` (e.g., `tauri-v0.4.0-beta.1`) are automatically marked as prerelease in GitHub Releases. The version detection script handles this:

```bash
PRERELEASE="false"
if [[ "$VERSION" == *-* ]]; then
  PRERELEASE="true"
fi
if [[ "$INPUT_PRERELEASE" == "true" ]]; then
  PRERELEASE="true"
fi
```

### Stable users do not see prereleases

GitHub's `/releases/latest/` endpoint skips prerelease releases. Since the updater endpoint URL uses this path:

```
https://github.com/OWNER/REPO/releases/latest/download/latest.json
```

Stable users' apps never fetch a prerelease `latest.json`.

### Beta channel

To allow beta testers to receive prerelease updates, add a second endpoint pointing to a specific tag:

```json
{
  "plugins": {
    "updater": {
      "endpoints": [
        "https://github.com/OWNER/REPO/releases/download/tauri-v0.4.0-beta.1/latest.json",
        "https://github.com/OWNER/REPO/releases/latest/download/latest.json"
      ]
    }
  }
}
```

The updater tries endpoints in order. Beta testers get a build with the beta endpoint first; if it fails (tag deleted, network error), they fall back to the stable channel.

In practice, managing a true beta channel requires maintaining a separate build configuration or a feature flag that swaps the endpoints array. A simpler approach is to have beta testers install prerelease builds manually and rely on the standard updater for subsequent beta-to-beta updates (since each prerelease also generates `latest.json`).

---

## 12. Troubleshooting

### "Update check failed" or banner never appears

1. **Is `config.isTauri` true?** The banner only renders in desktop Tauri builds. Check `"__TAURI_INTERNALS__" in window` in the browser console.
2. **Is the endpoint URL correct?** Must be a direct download URL to `latest.json`, not an HTML page. Test: `curl -L <endpoint-url>` should return JSON.
3. **CSP blocking?** Check that `connect-src` includes `https:` in `tauri.conf.json`. Open DevTools in the Tauri window (enabled by the `devtools` feature) to check for CSP violation errors.
4. **Permissions?** Check `capabilities/default.json` has `updater:default`.
5. **Same version?** If the app version matches `latest.json`, the updater correctly reports no update. Bump the version to test.

### "Signature verification failed"

- The pubkey in `tauri.conf.json` does not match the private key used to sign the release.
- Regenerate keys and update both the config (pubkey) and GitHub secrets (private key).
- Verify the `.sig` file content in `latest.json` matches the actual `.sig` file in the release assets.

### Update downloads but "Restart" does not work

- Check `capabilities/default.json` has `process:allow-restart`.
- Check `tauri-plugin-process` is in `Cargo.toml` dependencies.
- Check `.plugin(tauri_plugin_process::init())` is in `lib.rs`.

### CI build succeeds but no `latest.json` in release

- The `release` job only runs after all 3 platform builds succeed.
- If any platform build fails to produce `.sig` files, that platform is excluded from `latest.json`.
- If ALL builds fail to produce `.sig` files, the `latest.json` generation fails entirely.
- Check that `TAURI_SIGNING_PRIVATE_KEY` secret is set in GitHub (Settings > Secrets > Actions).
- Check the "Validate updater config" step -- if the pubkey is still a placeholder, the build exits early.

### Stale artifacts from previous builds

The workflow includes a cleanup step that removes old bundle artifacts before building:

```bash
find frontend/src-tauri/target -path '*/release/bundle' -type d -exec rm -rf {} + 2>/dev/null || true
```

Without this, artifact globbing (`*.app.tar.gz`, `*-setup.exe`) might pick up files from a previous build, causing version mismatches in `latest.json`.

### macOS "damaged" or "unidentified developer" warning

This is unrelated to minisign signing. macOS requires Apple Developer codesigning and notarization for apps distributed outside the App Store. Tauri's minisign signing only protects the update channel. To eliminate macOS warnings:

1. Enroll in the Apple Developer Program ($99/year)
2. Add `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD`, and `APPLE_TEAM_ID` to GitHub secrets
3. Tauri CLI handles codesigning and notarization automatically when these variables are present

### Prerelease versions not appearing to testers

- Verify the tag was created with a `-` in the version (e.g., `tauri-v0.4.0-beta.1`)
- Verify the release is marked as "Pre-release" in GitHub Releases
- Remember: `/releases/latest/` skips prereleases by design -- testers need a direct endpoint URL

---

## File Reference

| File | Purpose |
|------|---------|
| `frontend/src-tauri/tauri.conf.json` | Updater config: pubkey, endpoints, createUpdaterArtifacts, version |
| `frontend/src-tauri/Cargo.toml` | Rust deps: `tauri-plugin-updater`, `tauri-plugin-process` |
| `frontend/src-tauri/src/lib.rs` | Plugin initialization in `.setup()` with `#[cfg(desktop)]` |
| `frontend/src-tauri/capabilities/default.json` | Permissions: `updater:default`, `process:allow-restart` |
| `frontend/src/lib/updater.ts` | JS wrapper: check, download, relaunch (dynamic imports) |
| `frontend/src/components/layout/UpdateBanner.tsx` | UI: state machine banner with retry, dismiss, progress |
| `.github/workflows/tauri-build.yml` | CI: build matrix, sign, generate latest.json, GitHub Release |
