# TODO

## WASM Browser Rust Wiring

**Plan:** `docs/superpowers/plans/2026-03-17-wasm-browser-rust-wiring.md`

Compile `crates/processing` to WebAssembly so the browser (WASM mode) uses Rust for bar extraction and line-based grid detection instead of the Canvas JS ports (~20-30x speedup). Tesseract.js stays for OCR.

Tasks (in order):
- [ ] W1: Make `leptess` optional in `crates/processing` via `ocr` feature flag
- [ ] W2: Create `crates/wasm-bindings` crate with wasm-bindgen exports
- [ ] W3: `scripts/build-wasm.sh` + `build:wasm` npm script
- [ ] W4: `frontend/src/core/implementations/wasm/processing/screenshotProcessorWasm.ts` wrapper
- [ ] W5: Wire WASM into `imageProcessor.worker.canvas.ts` (bar extraction + line-based grid detection)
- [ ] W6: Add Rust + wasm-pack to `docker/frontend/Dockerfile` build stage
