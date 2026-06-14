import re


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

    patterns = [
        r"\b2160p\b",
        r"\b1440p\b",
        r"\b1080p\b",
        r"\b720p\b",
        r"\b480p\b",
        r"\bWEB[- ]DL\b",
        r"\bBluRay\b",
        r"\bHDRip\b",
        r"\bHindi\b",
        r"\bEnglish\b",
        r"\bDual Audio\b",
        r"\b\d{4}\b",
    ]

    for pattern in patterns:
        title = re.sub(
            pattern,
            "",
            title,
            flags=re.I,
        )

    title = title.replace(".", " ")

    title = re.sub(
        r"\b(x264|x265|AAC|HEVC)\b",
        "",
        title,
        flags=re.I,
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    return title.strip()


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