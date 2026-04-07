"""iPhone device profiles."""

from ..core.types import DeviceCategory, DeviceFamily
from .registry import DeviceProfile

# iPhone SE Series
IPHONE_SE_1ST = DeviceProfile(
    profile_id="iphone_se_1st",
    model_name="iPhone SE (1st generation)",
    display_name="iPhone SE",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_SE,
    screen_width_points=320,
    screen_height_points=568,
    scale_factor=2,
)

IPHONE_SE_2ND = DeviceProfile(
    profile_id="iphone_se_2nd",
    model_name="iPhone SE (2nd generation)",
    display_name="iPhone SE (2020)",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_SE,
    screen_width_points=375,
    screen_height_points=667,
    scale_factor=2,
)

IPHONE_SE_3RD = DeviceProfile(
    profile_id="iphone_se_3rd",
    model_name="iPhone SE (3rd generation)",
    display_name="iPhone SE (2022)",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_SE,
    screen_width_points=375,
    screen_height_points=667,
    scale_factor=2,
)

# iPhone 6/7/8 Series (Standard)
IPHONE_6 = DeviceProfile(
    profile_id="iphone_6",
    model_name="iPhone 6",
    display_name="iPhone 6",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_STANDARD,
    screen_width_points=375,
    screen_height_points=667,
    scale_factor=2,
)

IPHONE_6_PLUS = DeviceProfile(
    profile_id="iphone_6_plus",
    model_name="iPhone 6 Plus",
    display_name="iPhone 6 Plus",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PLUS,
    screen_width_points=414,
    screen_height_points=736,
    scale_factor=3,
)

IPHONE_7 = DeviceProfile(
    profile_id="iphone_7",
    model_name="iPhone 7",
    display_name="iPhone 7",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_STANDARD,
    screen_width_points=375,
    screen_height_points=667,
    scale_factor=2,
)

IPHONE_7_PLUS = DeviceProfile(
    profile_id="iphone_7_plus",
    model_name="iPhone 7 Plus",
    display_name="iPhone 7 Plus",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PLUS,
    screen_width_points=414,
    screen_height_points=736,
    scale_factor=3,
)

IPHONE_8 = DeviceProfile(
    profile_id="iphone_8",
    model_name="iPhone 8",
    display_name="iPhone 8",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_STANDARD,
    screen_width_points=375,
    screen_height_points=667,
    scale_factor=2,
)

IPHONE_8_PLUS = DeviceProfile(
    profile_id="iphone_8_plus",
    model_name="iPhone 8 Plus",
    display_name="iPhone 8 Plus",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PLUS,
    screen_width_points=414,
    screen_height_points=736,
    scale_factor=3,
)

# iPhone X Series
IPHONE_X = DeviceProfile(
    profile_id="iphone_x",
    model_name="iPhone X",
    display_name="iPhone X",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO,
    screen_width_points=375,
    screen_height_points=812,
    scale_factor=3,
)

IPHONE_XS = DeviceProfile(
    profile_id="iphone_xs",
    model_name="iPhone XS",
    display_name="iPhone XS",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO,
    screen_width_points=375,
    screen_height_points=812,
    scale_factor=3,
)

IPHONE_XS_MAX = DeviceProfile(
    profile_id="iphone_xs_max",
    model_name="iPhone XS Max",
    display_name="iPhone XS Max",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO_MAX,
    screen_width_points=414,
    screen_height_points=896,
    scale_factor=3,
)

IPHONE_XR = DeviceProfile(
    profile_id="iphone_xr",
    model_name="iPhone XR",
    display_name="iPhone XR",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_STANDARD,
    screen_width_points=414,
    screen_height_points=896,
    scale_factor=2,
)

# iPhone 11 Series
IPHONE_11 = DeviceProfile(
    profile_id="iphone_11",
    model_name="iPhone 11",
    display_name="iPhone 11",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_STANDARD,
    screen_width_points=414,
    screen_height_points=896,
    scale_factor=2,
)

IPHONE_11_PRO = DeviceProfile(
    profile_id="iphone_11_pro",
    model_name="iPhone 11 Pro",
    display_name="iPhone 11 Pro",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO,
    screen_width_points=375,
    screen_height_points=812,
    scale_factor=3,
)

IPHONE_11_PRO_MAX = DeviceProfile(
    profile_id="iphone_11_pro_max",
    model_name="iPhone 11 Pro Max",
    display_name="iPhone 11 Pro Max",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO_MAX,
    screen_width_points=414,
    screen_height_points=896,
    scale_factor=3,
)

# iPhone 12 Series
IPHONE_12_MINI = DeviceProfile(
    profile_id="iphone_12_mini",
    model_name="iPhone 12 mini",
    display_name="iPhone 12 mini",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_MINI,
    screen_width_points=375,
    screen_height_points=812,
    scale_factor=3,
)

IPHONE_12 = DeviceProfile(
    profile_id="iphone_12",
    model_name="iPhone 12",
    display_name="iPhone 12",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_STANDARD,
    screen_width_points=390,
    screen_height_points=844,
    scale_factor=3,
)

IPHONE_12_PRO = DeviceProfile(
    profile_id="iphone_12_pro",
    model_name="iPhone 12 Pro",
    display_name="iPhone 12 Pro",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO,
    screen_width_points=390,
    screen_height_points=844,
    scale_factor=3,
)

IPHONE_12_PRO_MAX = DeviceProfile(
    profile_id="iphone_12_pro_max",
    model_name="iPhone 12 Pro Max",
    display_name="iPhone 12 Pro Max",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO_MAX,
    screen_width_points=428,
    screen_height_points=926,
    scale_factor=3,
)

# iPhone 13 Series
IPHONE_13_MINI = DeviceProfile(
    profile_id="iphone_13_mini",
    model_name="iPhone 13 mini",
    display_name="iPhone 13 mini",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_MINI,
    screen_width_points=375,
    screen_height_points=812,
    scale_factor=3,
)

IPHONE_13 = DeviceProfile(
    profile_id="iphone_13",
    model_name="iPhone 13",
    display_name="iPhone 13",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_STANDARD,
    screen_width_points=390,
    screen_height_points=844,
    scale_factor=3,
)

IPHONE_13_PRO = DeviceProfile(
    profile_id="iphone_13_pro",
    model_name="iPhone 13 Pro",
    display_name="iPhone 13 Pro",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO,
    screen_width_points=390,
    screen_height_points=844,
    scale_factor=3,
)

IPHONE_13_PRO_MAX = DeviceProfile(
    profile_id="iphone_13_pro_max",
    model_name="iPhone 13 Pro Max",
    display_name="iPhone 13 Pro Max",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO_MAX,
    screen_width_points=428,
    screen_height_points=926,
    scale_factor=3,
)

# iPhone 14 Series
IPHONE_14 = DeviceProfile(
    profile_id="iphone_14",
    model_name="iPhone 14",
    display_name="iPhone 14",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_STANDARD,
    screen_width_points=390,
    screen_height_points=844,
    scale_factor=3,
)

IPHONE_14_PLUS = DeviceProfile(
    profile_id="iphone_14_plus",
    model_name="iPhone 14 Plus",
    display_name="iPhone 14 Plus",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PLUS,
    screen_width_points=428,
    screen_height_points=926,
    scale_factor=3,
)

IPHONE_14_PRO = DeviceProfile(
    profile_id="iphone_14_pro",
    model_name="iPhone 14 Pro",
    display_name="iPhone 14 Pro",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO,
    screen_width_points=393,
    screen_height_points=852,
    scale_factor=3,
)

IPHONE_14_PRO_MAX = DeviceProfile(
    profile_id="iphone_14_pro_max",
    model_name="iPhone 14 Pro Max",
    display_name="iPhone 14 Pro Max",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO_MAX,
    screen_width_points=430,
    screen_height_points=932,
    scale_factor=3,
)

# iPhone 15 Series
IPHONE_15 = DeviceProfile(
    profile_id="iphone_15",
    model_name="iPhone 15",
    display_name="iPhone 15",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_STANDARD,
    screen_width_points=393,
    screen_height_points=852,
    scale_factor=3,
)

IPHONE_15_PLUS = DeviceProfile(
    profile_id="iphone_15_plus",
    model_name="iPhone 15 Plus",
    display_name="iPhone 15 Plus",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PLUS,
    screen_width_points=430,
    screen_height_points=932,
    scale_factor=3,
)

IPHONE_15_PRO = DeviceProfile(
    profile_id="iphone_15_pro",
    model_name="iPhone 15 Pro",
    display_name="iPhone 15 Pro",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO,
    screen_width_points=393,
    screen_height_points=852,
    scale_factor=3,
)

IPHONE_15_PRO_MAX = DeviceProfile(
    profile_id="iphone_15_pro_max",
    model_name="iPhone 15 Pro Max",
    display_name="iPhone 15 Pro Max",
    category=DeviceCategory.IPHONE,
    family=DeviceFamily.IPHONE_PRO_MAX,
    screen_width_points=430,
    screen_height_points=932,
    scale_factor=3,
)

# All iPhone profiles
IPHONE_PROFILES: list[DeviceProfile] = [
    # SE Series
    IPHONE_SE_1ST,
    IPHONE_SE_2ND,
    IPHONE_SE_3RD,
    # 6/7/8 Series
    IPHONE_6,
    IPHONE_6_PLUS,
    IPHONE_7,
    IPHONE_7_PLUS,
    IPHONE_8,
    IPHONE_8_PLUS,
    # X Series
    IPHONE_X,
    IPHONE_XS,
    IPHONE_XS_MAX,
    IPHONE_XR,
    # 11 Series
    IPHONE_11,
    IPHONE_11_PRO,
    IPHONE_11_PRO_MAX,
    # 12 Series
    IPHONE_12_MINI,
    IPHONE_12,
    IPHONE_12_PRO,
    IPHONE_12_PRO_MAX,
    # 13 Series
    IPHONE_13_MINI,
    IPHONE_13,
    IPHONE_13_PRO,
    IPHONE_13_PRO_MAX,
    # 14 Series
    IPHONE_14,
    IPHONE_14_PLUS,
    IPHONE_14_PRO,
    IPHONE_14_PRO_MAX,
    # 15 Series
    IPHONE_15,
    IPHONE_15_PLUS,
    IPHONE_15_PRO,
    IPHONE_15_PRO_MAX,
]
