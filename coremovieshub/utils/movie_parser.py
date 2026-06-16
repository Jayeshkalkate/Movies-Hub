import re
import logging

logger = logging.getLogger(__name__)


def clean_caption(text):
    """
    Remove Telegram promotions, usernames,
    and invite links from captions.
    """
    if not text:
        return ""

    text = str(text)

    text = re.sub(
        r"(?i)\bjoin\b.*",
        "",
        text,
    )

    text = re.sub(
        r"@\w+",
        "",
        text,
    )

    text = re.sub(
        r"t\.me/\S+",
        "",
        text,
    )

    return text.strip()


def extract_title(text):
    """
    Extract a clean movie title
    from Telegram captions.
    """

    if not text:
        return ""

    title = str(text).split("\n")[0]

    title = title.replace(".", " ")
    title = title.replace("-", " ")
    title = title.replace("_", " ")

    patterns = [
        # Resolutions
        r"\b2160p\b",
        r"\b1440p\b",
        r"\b1080p\b",
        r"\b720p\b",
        r"\b480p\b",

        # Source / Release type
        r"\bWEB[- ]DL\b",
        r"\bWEBRip\b",
        r"\bBluRay\b",
        r"\bHDRip\b",
        r"\bDVDRip\b",

        # Languages
        r"\bHindi\b",
        r"\bEnglish\b",
        r"\bTamil\b",
        r"\bTelugu\b",
        r"\bMalayalam\b",

        # Audio / subtitle flags
        r"\bDual Audio\b",
        r"\bORG\b",
        r"\bDubbed\b",
        r"\bESub\b",

        # Codec / bit depth
        r"\b10bit\b",
        r"\bHEVC\b",
        r"\bAAC\b",
        r"\bDDP\b",

        r"\bx264\b",
        r"\bx265\b",

        # Audio channels
        r"\b2CH\b",
        r"\b5\.1\b",

        # Group tags
        r"\bPSA\b",

        # File extensions
        r"\bmkv\b",
        r"\bmp4\b",
        r"\bavi\b",

        # Telegram spam
        r"JOIN\s+@\w+",

        # --- NEW PATTERNS for seasons, episodes, series, and streamers ---
        r"\bSeason\s*\d+\b",
        r"\bS\d+\b",               # S01, S2, etc.
        r"\bE\d+\b",               # E01, E5, etc.
        r"\bEpisode\s*\d+\b",
        r"\bComplete\b",
        r"\bNF\b",                 # Netflix
        r"\bAMZN\b",               # Amazon
    ]

    for pattern in patterns:
        title = re.sub(
            pattern,
            "",
            title,
            flags=re.I,
        )

    # Remove years (1900-2099)
    title = re.sub(
        r"\b(19|20)\d{2}\b",
        "",
        title,
    )

    # Log the cleaned title (instead of print)
    cleaned = title.strip()
    logger.info(f"Extracted title: '{cleaned}'")
    return cleaned


def extract_season(text):
    """
    Extract season number from text.
    Examples:
    S01 -> 1
    Season 2 -> 2
    """
    if not text:
        return None

    text = str(text)

    match = re.search(
        r"(?:S|Season\s*)(\d+)",
        text,
        re.I,
    )

    if match:
        return int(match.group(1))

    return None


def extract_quality(text):
    """
    Extract video quality.
    """
    if not text:
        return "Unknown"

    text = str(text).lower()

    for quality in [
        "2160p",
        "1440p",
        "1080p",
        "720p",
        "480p",
    ]:
        if quality in text:
            return quality

    return "Unknown"


def extract_language(text):
    """
    Extract audio language information.
    """
    if not text:
        return ""

    lower = str(text).lower()

    if "dual audio" in lower:
        return "Dual Audio"

    if "hindi" in lower:
        return "Hindi"

    if "english" in lower:
        return "English"

    return ""