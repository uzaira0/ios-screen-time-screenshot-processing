"""Device profile registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..core.types import DeviceCategory, DeviceFamily, ScreenDimensions


@dataclass(frozen=True)
class DeviceProfile:
    """Profile for a specific iOS device model."""

    profile_id: str
    model_name: str
    display_name: str
    category: DeviceCategory
    family: DeviceFamily

    # Screen specifications
    screen_width_points: int
    screen_height_points: int
    scale_factor: int  # 1, 2, or 3

    # Computed screenshot dimensions (points * scale)
    @property
    def screenshot_dimensions(self) -> ScreenDimensions:
        """Get expected screenshot dimensions in pixels."""
        return ScreenDimensions(
            width=self.screen_width_points * self.scale_factor,
            height=self.screen_height_points * self.scale_factor,
        )

    @property
    def aspect_ratio(self) -> float:
        """Get aspect ratio (height/width)."""
        return self.screen_height_points / self.screen_width_points


class ProfileRegistry:
    """Registry for device profiles."""

    _instance: "ProfileRegistry | None" = None

    def __init__(self) -> None:
        self._profiles: dict[str, DeviceProfile] = {}
        self._by_dimensions: dict[tuple[int, int], list[DeviceProfile]] = {}

    @classmethod
    def get_instance(cls) -> "ProfileRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_default_profiles()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    def register(self, profile: DeviceProfile) -> None:
        """Register a device profile."""
        self._profiles[profile.profile_id] = profile

        # Index by dimensions
        dims = profile.screenshot_dimensions
        key = (dims.width, dims.height)

        if key not in self._by_dimensions:
            self._by_dimensions[key] = []
        self._by_dimensions[key].append(profile)

    def get_profile(self, profile_id: str) -> DeviceProfile | None:
        """Get profile by ID."""
        return self._profiles.get(profile_id)

    def get_profiles_by_dimensions(
        self, width: int, height: int
    ) -> list[DeviceProfile]:
        """Get all profiles matching exact dimensions."""
        return self._by_dimensions.get((width, height), [])

    def get_all_profiles(self) -> Iterator[DeviceProfile]:
        """Get all registered profiles."""
        return iter(self._profiles.values())

    def get_iphone_profiles(self) -> list[DeviceProfile]:
        """Get all iPhone profiles."""
        return [
            p for p in self._profiles.values()
            if p.category == DeviceCategory.IPHONE
        ]

    def get_ipad_profiles(self) -> list[DeviceProfile]:
        """Get all iPad profiles."""
        return [
            p for p in self._profiles.values()
            if p.category == DeviceCategory.IPAD
        ]

    def _register_default_profiles(self) -> None:
        """Register all default device profiles."""
        from .iphone import IPHONE_PROFILES
        from .ipad import IPAD_PROFILES

        for profile in IPHONE_PROFILES:
            self.register(profile)

        for profile in IPAD_PROFILES:
            self.register(profile)


def get_profile_registry() -> ProfileRegistry:
    """Get the global profile registry."""
    return ProfileRegistry.get_instance()
