"""Device profile definitions for iOS devices."""

from .registry import (
    DeviceProfile,
    ProfileRegistry,
    get_profile_registry,
)
from .iphone import IPHONE_PROFILES
from .ipad import IPAD_PROFILES

__all__ = [
    "DeviceProfile",
    "ProfileRegistry",
    "get_profile_registry",
    "IPHONE_PROFILES",
    "IPAD_PROFILES",
]
