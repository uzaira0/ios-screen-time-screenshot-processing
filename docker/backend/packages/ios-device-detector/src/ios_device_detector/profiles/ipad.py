"""iPad device profiles."""

from ..core.types import DeviceCategory, DeviceFamily
from .registry import DeviceProfile

# iPad Standard
IPAD_9TH = DeviceProfile(
    profile_id="ipad_9th",
    model_name="iPad (9th generation)",
    display_name="iPad 9th Gen",
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_STANDARD,
    screen_width_points=810,
    screen_height_points=1080,
    scale_factor=2,
)

IPAD_10TH = DeviceProfile(
    profile_id="ipad_10th",
    model_name="iPad (10th generation)",
    display_name="iPad 10th Gen",
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_STANDARD,
    screen_width_points=820,
    screen_height_points=1180,
    scale_factor=2,
)

# iPad Mini
IPAD_MINI_5TH = DeviceProfile(
    profile_id="ipad_mini_5th",
    model_name="iPad mini (5th generation)",
    display_name="iPad mini 5",
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_MINI,
    screen_width_points=768,
    screen_height_points=1024,
    scale_factor=2,
)

IPAD_MINI_6TH = DeviceProfile(
    profile_id="ipad_mini_6th",
    model_name="iPad mini (6th generation)",
    display_name="iPad mini 6",
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_MINI,
    screen_width_points=744,
    screen_height_points=1133,
    scale_factor=2,
)

# iPad Air
IPAD_AIR_3RD = DeviceProfile(
    profile_id="ipad_air_3rd",
    model_name="iPad Air (3rd generation)",
    display_name="iPad Air 3",
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_AIR,
    screen_width_points=834,
    screen_height_points=1112,
    scale_factor=2,
)

IPAD_AIR_4TH = DeviceProfile(
    profile_id="ipad_air_4th",
    model_name="iPad Air (4th generation)",
    display_name="iPad Air 4",
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_AIR,
    screen_width_points=820,
    screen_height_points=1180,
    scale_factor=2,
)

IPAD_AIR_5TH = DeviceProfile(
    profile_id="ipad_air_5th",
    model_name="iPad Air (5th generation)",
    display_name="iPad Air 5",
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_AIR,
    screen_width_points=820,
    screen_height_points=1180,
    scale_factor=2,
)

# iPad Pro 11"
IPAD_PRO_11_1ST = DeviceProfile(
    profile_id="ipad_pro_11_1st",
    model_name="iPad Pro 11-inch (1st generation)",
    display_name='iPad Pro 11" (2018)',
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_PRO_11,
    screen_width_points=834,
    screen_height_points=1194,
    scale_factor=2,
)

IPAD_PRO_11_2ND = DeviceProfile(
    profile_id="ipad_pro_11_2nd",
    model_name="iPad Pro 11-inch (2nd generation)",
    display_name='iPad Pro 11" (2020)',
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_PRO_11,
    screen_width_points=834,
    screen_height_points=1194,
    scale_factor=2,
)

IPAD_PRO_11_3RD = DeviceProfile(
    profile_id="ipad_pro_11_3rd",
    model_name="iPad Pro 11-inch (3rd generation)",
    display_name='iPad Pro 11" (2021)',
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_PRO_11,
    screen_width_points=834,
    screen_height_points=1194,
    scale_factor=2,
)

IPAD_PRO_11_4TH = DeviceProfile(
    profile_id="ipad_pro_11_4th",
    model_name="iPad Pro 11-inch (4th generation)",
    display_name='iPad Pro 11" (2022)',
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_PRO_11,
    screen_width_points=834,
    screen_height_points=1194,
    scale_factor=2,
)

# iPad Pro 12.9"
IPAD_PRO_12_9_3RD = DeviceProfile(
    profile_id="ipad_pro_12_9_3rd",
    model_name="iPad Pro 12.9-inch (3rd generation)",
    display_name='iPad Pro 12.9" (2018)',
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_PRO_12_9,
    screen_width_points=1024,
    screen_height_points=1366,
    scale_factor=2,
)

IPAD_PRO_12_9_4TH = DeviceProfile(
    profile_id="ipad_pro_12_9_4th",
    model_name="iPad Pro 12.9-inch (4th generation)",
    display_name='iPad Pro 12.9" (2020)',
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_PRO_12_9,
    screen_width_points=1024,
    screen_height_points=1366,
    scale_factor=2,
)

IPAD_PRO_12_9_5TH = DeviceProfile(
    profile_id="ipad_pro_12_9_5th",
    model_name="iPad Pro 12.9-inch (5th generation)",
    display_name='iPad Pro 12.9" (2021)',
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_PRO_12_9,
    screen_width_points=1024,
    screen_height_points=1366,
    scale_factor=2,
)

IPAD_PRO_12_9_6TH = DeviceProfile(
    profile_id="ipad_pro_12_9_6th",
    model_name="iPad Pro 12.9-inch (6th generation)",
    display_name='iPad Pro 12.9" (2022)',
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_PRO_12_9,
    screen_width_points=1024,
    screen_height_points=1366,
    scale_factor=2,
)

# Legacy dimensions used in screenshot cropper (1620x2160)
# This is 810x1080 @ 2x scale - matches iPad 9th gen
IPAD_SCREENSHOT_LEGACY = DeviceProfile(
    profile_id="ipad_screenshot_legacy",
    model_name="iPad (Screenshot Format)",
    display_name="iPad Screenshot",
    category=DeviceCategory.IPAD,
    family=DeviceFamily.IPAD_STANDARD,
    screen_width_points=810,
    screen_height_points=1080,
    scale_factor=2,
)

# All iPad profiles
IPAD_PROFILES: list[DeviceProfile] = [
    # Standard
    IPAD_9TH,
    IPAD_10TH,
    # Mini
    IPAD_MINI_5TH,
    IPAD_MINI_6TH,
    # Air
    IPAD_AIR_3RD,
    IPAD_AIR_4TH,
    IPAD_AIR_5TH,
    # Pro 11"
    IPAD_PRO_11_1ST,
    IPAD_PRO_11_2ND,
    IPAD_PRO_11_3RD,
    IPAD_PRO_11_4TH,
    # Pro 12.9"
    IPAD_PRO_12_9_3RD,
    IPAD_PRO_12_9_4TH,
    IPAD_PRO_12_9_5TH,
    IPAD_PRO_12_9_6TH,
    # Legacy
    IPAD_SCREENSHOT_LEGACY,
]
