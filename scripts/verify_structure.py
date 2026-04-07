#!/usr/bin/env python3
"""
Simple structure verification that doesn't require dependencies.
"""

from __future__ import annotations

import ast
from pathlib import Path


def check_imports_in_file(file_path: Path, forbidden_imports: set[str]) -> bool:
    """Check if a Python file contains forbidden imports."""
    try:
        content = file_path.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(forbidden in alias.name for forbidden in forbidden_imports):
                        return False
            elif isinstance(node, ast.ImportFrom):
                if node.module and any(forbidden in node.module for forbidden in forbidden_imports):
                    return False

        return True
    except Exception as e:
        print(f"  Warning: Could not parse {file_path}: {e}")
        return True


def test_core_isolation():
    """Verify that core has no PyQt6 dependencies."""
    print("Testing core isolation...")

    core_dir = Path("src/screenshot_processor/core")
    forbidden = {"PyQt6", "PyQt5"}

    all_clear = True
    for py_file in core_dir.rglob("*.py"):
        if not check_imports_in_file(py_file, forbidden):
            print(f"  ❌ FAILED: Found PyQt in {py_file}")
            all_clear = False

    if all_clear:
        print("  ✅ PASSED: Core is framework-agnostic (no PyQt imports)")
    return all_clear


def test_file_structure():
    """Verify all expected files exist."""
    print("\nTesting file structure...")

    expected_files = [
        "src/screenshot_processor/__init__.py",
        "src/screenshot_processor/__main__.py",
        "src/screenshot_processor/core/__init__.py",
        "src/screenshot_processor/core/processor.py",
        "src/screenshot_processor/core/callbacks.py",
        "src/screenshot_processor/core/config.py",
        "src/screenshot_processor/core/models.py",
        "src/screenshot_processor/gui/__init__.py",
        "src/screenshot_processor/gui/main_window.py",
        "src/screenshot_processor/gui/ui_components.py",
        "src/screenshot_processor/gui/magnifying_label.py",
    ]

    all_exist = True
    for file_path in expected_files:
        if not Path(file_path).exists():
            print(f"  ❌ FAILED: Missing {file_path}")
            all_exist = False

    if all_exist:
        print(f"  ✅ PASSED: All {len(expected_files)} expected files exist")
    return all_exist


def test_gui_imports():
    """Verify GUI files have correct imports."""
    print("\nTesting GUI imports...")

    gui_files = list(Path("src/screenshot_processor/gui").glob("*.py"))
    all_correct = True

    for py_file in gui_files:
        if py_file.name == "__init__.py":
            continue

        content = py_file.read_text()

        if "from enums import" in content:
            print(f"  ❌ FAILED: {py_file} has old-style import 'from enums import'")
            all_correct = False
        elif "from issue import" in content:
            print(f"  ❌ FAILED: {py_file} has old-style import 'from issue import'")
            all_correct = False
        elif "from image_processor import" in content and "screenshot_processor" not in content:
            print(f"  ❌ FAILED: {py_file} has old-style import 'from image_processor import'")
            all_correct = False

        if (
            "from screenshot_processor.core" in content
            or "from .main_window import" in content
            or "from .ui_components import" in content
        ):
            continue
        else:
            if "import" in content and py_file.name != "__pycache__":
                pass

    if all_correct:
        print("  ✅ PASSED: GUI imports use new package structure")
    return all_correct


def test_syntax():
    """Test that all Python files have valid syntax."""
    print("\nTesting Python syntax...")

    all_valid = True
    for py_file in Path("src/screenshot_processor").rglob("*.py"):
        try:
            compile(py_file.read_text(), str(py_file), "exec")
        except SyntaxError as e:
            print(f"  ❌ FAILED: Syntax error in {py_file}: {e}")
            all_valid = False

    if all_valid:
        print("  ✅ PASSED: All Python files have valid syntax")
    return all_valid


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Screenshot Processor Structure Verification")
    print("=" * 60)

    tests = [
        test_core_isolation,
        test_file_structure,
        test_gui_imports,
        test_syntax,
    ]

    results = [test() for test in tests]

    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)

    if all(results):
        print("\n✅ All structure tests PASSED!")
        print("\nThe GUI wrapper is correctly structured:")
        print("  • Core is framework-agnostic (no PyQt6 in core/)")
        print("  • All expected files exist")
        print("  • GUI uses new package imports")
        print("  • All Python files have valid syntax")
        print("\nNext steps:")
        print("  1. Install dependencies: pip install -e .[gui]")
        print("  2. Test launch: python -m screenshot_processor.gui")
        print("  3. Test entry point: screenshot-gui")
        return 0
    else:
        print("\n❌ Some tests FAILED")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
