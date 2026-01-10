"""Prompt templates for LLM/LVM-based PHI detection.

Uses a three-part prompt structure:
- system_prompt: Role and task definition
- positive_prompt: What to detect (focus categories)
- negative_prompt: What to ignore (not PHI)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PromptStyle(StrEnum):
    """Prompt style for different use cases."""

    HIPAA_STRICT = "hipaa_strict"  # Maximum recall, flag anything uncertain
    BALANCED = "balanced"  # Balance precision and recall
    CONSERVATIVE = "conservative"  # High precision, minimize false positives


@dataclass
class PHIDetectionPrompt:
    """Three-part prompt for PHI detection.

    Attributes:
        system_prompt: Role definition and task context
        positive_prompt: Categories of PHI to detect
        negative_prompt: Categories to ignore (not PHI)
        style: Detection aggressiveness
    """

    system_prompt: str = """You are a PHI (Protected Health Information) detector for research data protection.
Your task is to identify personally identifying information in text or images.

IMPORTANT: Only extract the specific PHI text itself, not surrounding context.
For example, if you see "Sarah's iPad", extract "Sarah" as a PERSON, not the whole phrase.

Output JSON only:
{
    "entities": [
        {
            "text": "exact PHI text only",
            "type": "PERSON|OTHER",
            "confidence": 0.0-1.0,
            "reasoning": "brief explanation"
        }
    ]
}

If no PHI found: {"entities": []}"""

    positive_prompt: list[str] = field(
        default_factory=lambda: [
            # Personal names only — the only PHI that appears on Screen Time screenshots
            "Personal names of individuals (first names, last names, full names, nicknames)",
            "Names extracted from device names (e.g., 'Sarah' from 'Sarah's iPad', 'John's iPad', 'Mom's iPad')",
        ]
    )

    negative_prompt: list[str] = field(
        default_factory=lambda: [
            # App names - comprehensive list (NEVER PHI)
            "ALL app names are NEVER PHI - this includes but is not limited to:",
            "  - Social media: Instagram, TikTok, Facebook, FB, Messenger, Snapchat, Twitter/X, WhatsApp, Telegram, Discord, Reddit, Pinterest, LinkedIn, BeReal",
            "  - Video/streaming: YouTube, YT, YT Kids, Netflix, Hulu, Disney+, HBO Max, Prime Video, Peacock, Paramount+, Apple TV, Twitch, Roku",
            "  - Games: Roblox, Minecraft, Fortnite, Among Us, Candy Crush, Clash of Clans, PUBG, Call of Duty, FIFA, Madden, Pokemon GO, Genshin Impact",
            "  - Kids apps: PBS Kids, Nick Jr, ABCmouse, Khan Academy Kids, Duolingo, Noggin, YouTube Kids",
            "  - Utilities: Safari, Chrome, Firefox, Maps, Google Maps, Waze, Calendar, Mail, Notes, Reminders, Clock, Calculator, Weather, Files, Shortcuts",
            "  - System: Settings, Screen Time, App Store, Photos, Camera, Messages, FaceTime, Phone, Contacts, Health, Wallet, Find My, Home",
            "  - Music/Audio: Spotify, Apple Music, Pandora, SoundCloud, Audible, Podcasts, Amazon Music, Tidal",
            "  - Productivity: Microsoft Office, Word, Excel, PowerPoint, Google Docs, Sheets, Notion, Slack, Zoom, Teams, Trello, Asana",
            "Abbreviated or stylized app names (YT, FB, IG, TT, etc.) - these are app abbreviations, NOT initials of people",
            "Game names, game titles, in-game character names, and gaming terminology",
            # Dates and times in UI context (NOT PHI)
            "ALL dates shown in usage statistics, charts, or UI navigation (Today, Yesterday, Last 7 Days, weekly views, etc.)",
            "ALL times shown in status bars, usage charts, time labels (12 AM, 6 AM, 12 PM, 6 PM, 9:41, etc.)",
            "Usage duration displays (2h 30m, 45 minutes, 3 hours, daily average, weekly total)",
            "Date ranges for usage reports (This Week, Last Week, custom date ranges)",
            # UI elements (NOT PHI)
            "Operating system UI elements (buttons, menus, navigation bars, tab bars, toolbars)",
            "Battery percentage and signal strength indicators",
            "Carrier names in status bar (AT&T, Verizon, T-Mobile, etc.)",
            "App Store categories (Social, Entertainment, Games, Productivity, Education, Health & Fitness)",
            "Usage statistics labels (pickups, notifications, Screen Time, App Limits, Downtime)",
            "Brand names, company logos, and product names",
            "Version numbers, build information, and software update labels",
            "Standard iOS/Android UI text and system labels",
            "Chart axes, graph labels, and data visualization elements",
            "Notification counts and badge numbers",
        ]
    )

    style: PromptStyle = PromptStyle.BALANCED

    def build_full_prompt(self, content: str | None = None, is_vision: bool = False) -> str:
        """Build the complete prompt for LLM/LVM.

        Args:
            content: Text to analyze (for text mode) or None (for vision mode)
            is_vision: Whether this is for a vision model

        Returns:
            Complete formatted prompt
        """
        style_instruction = self._get_style_instruction()

        positive_section = "\n".join(f"- {cat}" for cat in self.positive_prompt)
        negative_section = "\n".join(f"- {cat}" for cat in self.negative_prompt)

        prompt = f"""{self.system_prompt}

{style_instruction}

## DETECT (flag these as PHI):
{positive_section}

## IGNORE (these are NOT PHI):
{negative_section}

## Key Examples:
- "Safari" is an app name -> IGNORE
- "YT Kids" is an app name -> IGNORE
- "YouTube Kids" is an app name -> IGNORE
- "Roblox" is an app/game name -> IGNORE
- "Sarah's iPad" contains name "Sarah" -> DETECT "Sarah" as PERSON
- "SmithFamilyWiFi" contains name "Smith" -> DETECT "Smith" as PERSON
- "Screen Time" is an app name -> IGNORE
- "2h 30m" is usage time -> IGNORE
- "john.doe@email.com" -> IGNORE (email addresses do not appear on Screen Time screenshots)
- Time in status bar (e.g., "9:41") -> IGNORE
- "iPhone", "iPad", or "ipad" alone (no name) -> IGNORE
- "John's ipad", "John's IPAD", "Johns ipad" -> DETECT "John" as PERSON"""

        if is_vision:
            prompt += """

## Vision Instructions:
- Scan the entire image systematically
- Pay attention to status bar, device names, WiFi names, contact names
- If text is unclear, note low confidence
- Approximate location: top/middle/bottom, left/center/right"""
        elif content:
            prompt += f"""

## Text to Analyze:
\"\"\"
{content}
\"\"\""""

        return prompt

    def _get_style_instruction(self) -> str:
        """Get style-specific instruction."""
        if self.style == PromptStyle.HIPAA_STRICT:
            return """## Mode: STRICT (HIPAA Compliance)
When in doubt, FLAG IT. Better to have false positives than miss PHI."""

        elif self.style == PromptStyle.CONSERVATIVE:
            return """## Mode: CONSERVATIVE (High Precision)
Only flag items you are highly confident are PHI. Avoid false positives."""

        else:  # BALANCED
            return """## Mode: BALANCED
Flag items that are likely PHI with reasonable confidence."""

    def with_positive(self, *categories: str) -> PHIDetectionPrompt:
        """Add to positive prompt (what to detect)."""
        new_positive = list(self.positive_prompt) + list(categories)
        return PHIDetectionPrompt(
            system_prompt=self.system_prompt,
            positive_prompt=new_positive,
            negative_prompt=self.negative_prompt,
            style=self.style,
        )

    def with_negative(self, *categories: str) -> PHIDetectionPrompt:
        """Add to negative prompt (what to ignore)."""
        new_negative = list(self.negative_prompt) + list(categories)
        return PHIDetectionPrompt(
            system_prompt=self.system_prompt,
            positive_prompt=self.positive_prompt,
            negative_prompt=new_negative,
            style=self.style,
        )

    def with_system(self, system_prompt: str) -> PHIDetectionPrompt:
        """Override system prompt."""
        return PHIDetectionPrompt(
            system_prompt=system_prompt,
            positive_prompt=self.positive_prompt,
            negative_prompt=self.negative_prompt,
            style=self.style,
        )

    def with_style(self, style: PromptStyle) -> PHIDetectionPrompt:
        """Set detection style."""
        return PHIDetectionPrompt(
            system_prompt=self.system_prompt,
            positive_prompt=self.positive_prompt,
            negative_prompt=self.negative_prompt,
            style=style,
        )


# Pre-built prompt configurations
PROMPTS = {
    "default": PHIDetectionPrompt(),
    "hipaa": PHIDetectionPrompt(style=PromptStyle.HIPAA_STRICT),
    "conservative": PHIDetectionPrompt(style=PromptStyle.CONSERVATIVE),
    "screen_time": PHIDetectionPrompt(
        positive_prompt=[
            # Personal names only — the only PHI that realistically appears on Screen Time screenshots
            "Device names showing ownership regardless of capitalisation (e.g., 'Sarah's iPad', 'John's ipad', 'Mom's IPAD', 'Dad's iPad')",
            "Any first name, last name, or nickname of a person visible anywhere in the UI",
        ],
        negative_prompt=[
            # Comprehensive app list
            "ALL app names are NEVER PHI including: Instagram, TikTok, Facebook, Snapchat, YouTube, YT, YT Kids, Safari, Chrome, Netflix, Disney+, Hulu, Roblox, Minecraft, Fortnite, Spotify, Messages, FaceTime, Phone, Mail, Calendar, Photos, Camera, Settings, Screen Time, App Store, Health, Wallet, Maps, Notes, Reminders, Clock, Weather, News, Stocks, Books, Podcasts, TV, Music, Files, Shortcuts, Home, Find My, Contacts, etc.",
            "Abbreviated app names (YT, FB, IG, TT, etc.) - these are app abbreviations, NOT people's initials",
            "Game names, game titles, and gaming terminology",
            # Time/date in UI (NOT PHI)
            "ALL times in status bar, charts, or usage displays (9:41, 12 AM, 6 PM, etc.)",
            "ALL dates in usage statistics (Today, Yesterday, This Week, Last 7 Days, etc.)",
            "Usage durations (2h 30m, 45 minutes, daily average, weekly total)",
            # UI elements
            "iOS/iPadOS UI elements, navigation bars, tab bars, buttons, menus",
            "Bar charts, graphs, pie charts, and usage visualizations",
            "Chart labels and axes (time labels, percentage labels)",
            "App categories (Social, Entertainment, Games, Productivity, Education, Health & Fitness)",
            "Notification counts, pickup counts, badge numbers",
            "Battery percentage and signal strength",
            "Carrier names (AT&T, Verizon, T-Mobile, etc.)",
            "Screen Time labels (App Limits, Downtime, Always Allowed, Content & Privacy)",
        ],
        style=PromptStyle.BALANCED,
    ),
    "messages": PHIDetectionPrompt(
        positive_prompt=[
            "Contact names in conversation",
            "Personal names mentioned in messages",
            "Phone numbers",
            "Email addresses",
            "Physical addresses",
            "Any identifying information about individuals",
        ],
        negative_prompt=[
            "App UI elements",
            "Timestamps",
            "Read receipts",
            "Typing indicators",
        ],
    ),
}


def get_prompt(name: str = "default") -> PHIDetectionPrompt:
    """Get a pre-built prompt configuration.

    Args:
        name: Prompt configuration name

    Returns:
        PHIDetectionPrompt instance
    """
    if name not in PROMPTS:
        available = ", ".join(PROMPTS.keys())
        raise ValueError(f"Unknown prompt '{name}'. Available: {available}")
    return PROMPTS[name]
