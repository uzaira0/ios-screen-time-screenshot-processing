//! Rust-native image processing pipeline for iOS Screen Time screenshots.
//!
//! This module ports the Python image processing pipeline to Rust for
//! self-contained desktop processing without needing the Python backend.

pub mod bar_extraction;
pub mod boundary_optimizer;
pub mod grid_detection;
pub mod image_utils;
pub mod ocr;
pub mod pipeline;
pub mod types;

pub use pipeline::{extract_hourly_data, process_image, process_image_optimized, process_image_with_grid};
pub use types::{GridBounds, ProcessingError, ProcessingResult};
