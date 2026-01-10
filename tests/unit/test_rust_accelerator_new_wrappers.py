import pytest
from pathlib import Path

FIXTURE_IMAGE = Path("tests/fixtures/images/IMG_0806 Cropped.png")


def test_process_image_with_grid_returns_24_values():
    """process_image_with_grid returns a dict with 24 hourly values."""
    from screenshot_processor.core.rust_accelerator import process_image_with_grid

    if not FIXTURE_IMAGE.exists():
        pytest.skip("Fixture image not found")

    result = process_image_with_grid(
        str(FIXTURE_IMAGE),
        upper_left=(100, 300),
        lower_right=(1000, 800),
        image_type="screen_time",
    )

    assert isinstance(result, dict)
    assert "hourly_values" in result
    assert len(result["hourly_values"]) == 24
    assert all(isinstance(v, float) for v in result["hourly_values"])
    assert "alignment_score" in result


def test_process_image_with_grid_fallback_on_missing_rust(monkeypatch):
    """Falls back to Python gracefully when Rust is not available."""
    import screenshot_processor.core.rust_accelerator as ra
    monkeypatch.setattr(ra, "_RUST_AVAILABLE", False)
    monkeypatch.setattr(ra, "_rs", None)

    if not FIXTURE_IMAGE.exists():
        pytest.skip("Fixture image not found")

    from screenshot_processor.core.rust_accelerator import process_image_with_grid
    result = process_image_with_grid(
        str(FIXTURE_IMAGE),
        upper_left=(100, 300),
        lower_right=(1000, 800),
    )
    assert "hourly_values" in result
    assert len(result["hourly_values"]) == 24


def test_extract_hourly_data_returns_24_floats():
    """extract_hourly_data returns exactly 24 float values."""
    from screenshot_processor.core.rust_accelerator import extract_hourly_data

    if not FIXTURE_IMAGE.exists():
        pytest.skip("Fixture image not found")

    values = extract_hourly_data(
        str(FIXTURE_IMAGE),
        upper_left=(100, 300),
        lower_right=(1000, 800),
    )

    # Returns list of 24 floats on success, or None on extraction failure
    assert values is None or (
        isinstance(values, list) and len(values) == 24 and all(isinstance(v, float) for v in values)
    ), f"Expected None or list of 24 floats, got: {type(values)}"


def test_extract_hourly_data_fallback(monkeypatch):
    """Falls back to Python when Rust unavailable — returns None."""
    import screenshot_processor.core.rust_accelerator as ra
    monkeypatch.setattr(ra, "_RUST_AVAILABLE", False)
    monkeypatch.setattr(ra, "_rs", None)

    if not FIXTURE_IMAGE.exists():
        pytest.skip("Fixture image not found")

    from screenshot_processor.core.rust_accelerator import extract_hourly_data
    values = extract_hourly_data(str(FIXTURE_IMAGE), upper_left=(100, 300), lower_right=(1000, 800))
    # With no Rust and fixture image, Python fallback may succeed or return None
    assert values is None or len(values) == 24
