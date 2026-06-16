import re
import logging

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# 1. COMBINED PATTERN – all metadata in one regex
#    (case‑insensitive, compiled once for performance)
# -------------------------------------------------------------------
METADATA_PATTERNS = [
    # Resolution
    r"\b2160p\b", r"\b1440p\b", r"\b1080p\b", r"\b720p\b", r"\b480p\b",
    # Source
    r"\bWEB[- ]DL\b", r"\bWEBRip\b", r"\bBluRay\b", r"\bHDRip\b", r"\bDVDRip\b",
    # Languages
    r"\bHindi\b", r"\bEnglish\b", r"\bTamil\b", r"\bTelugu\b", r"\bMalayalam\b",
    # Audio / Subtitle flags
    r"\bDual Audio\b", r"\bORG\b", r"\bDubbed\b", r"\bESub\b",
    # Codec & bit depth
    r"\b10bit\b", r"\bHEVC\b", r"\bAAC\b", r"\bDDP\b",
    # Video codec
    r"\bx264\b", r"\bx265\b",
    # Audio channels
    r"\b2CH\b", r"\b5\.1\b",
    # Release group
    r"\bPSA\b",
    # File extensions
    r"\bmkv\b", r"\bmp4\b", r"\bavi\b",
    # Spam / promotions (intentionally without word boundaries)
    r"JOIN\s+@\w+",
    # Season / Episode / Part
    r"\bSeason\s*\d+\b", r"\bS\d+\b",
    r"\bEpisode\s*\d+\b", r"\bE\d+\b",
    r"\bPart\s*\d+\b",
    # Miscellaneous
    r"\bComplete\b", r"\bSeries\b",
    r"\bMulti Audio\b", r"\bMultiAudio\b",
    # Year (four digits, 1900–2099)
    r"\b(?:19|20)\d{2}\b",

    # ---------- ADDED PATTERNS TO FIX SPIDER-MAN PARSING ----------
    r"\bDD\s*\d+\s*\d+\b",          # "DD 5 1", "DD5.1", etc.
    r"\bAAC\s*\d+\s*\d+\b",         # "AAC 5.1"
    r"\bNF\b",                      # Netflix
    r"\bHE\b",                      # maybe "HE" as in HEVC? but we keep it
    r"\bImmortal\b",                # group name
    r"\bGodfather\b",               # group name (some releases use this)
    r"\bYTS\b",                     # YIFY group
    r"\bAM\b",                      # group or audio codec?
    r"\bORG\b",                     # already present, but re-added for clarity
    r"\bor\b",                      # standalone "or" (common spam)
    r"\bDual Audio\b",              # already present
    r"\bESubs?\b",                  # matches "ESub" or "ESubs"
]

# Compile once, reuse everywhere
_METADATA_RE = re.compile(
    "|".join(f"(?:{p})" for p in METADATA_PATTERNS),
    re.IGNORECASE,
)

# -------------------------------------------------------------------
# 2. CLEANING & EXTRACTION FUNCTIONS
# -------------------------------------------------------------------

def clean_caption(text):
    """
    Remove Telegram promotions, usernames, and invite links from captions.
    """
    if not text:
        return ""

    text = str(text)

    # Remove lines starting with "join" (case‑insensitive)
    text = re.sub(r"(?i)\bjoin\b.*", "", text)
    # Remove @usernames
    text = re.sub(r"@\w+", "", text)
    # Remove t.me/ links
    text = re.sub(r"t\.me/\S+", "", text)

    return text.strip()


def extract_title(text):
    """
    Extract a clean movie title from Telegram captions.
    Uses a single regex to strip all metadata at once.
    """
    if not text:
        return ""

    # Take the first line and clean separators
    title = str(text).split("\n")[0]
    title = title.replace(".", " ").replace("-", " ").replace("_", " ")

    # Remove all metadata patterns in one pass
    title = _METADATA_RE.sub("", title)

    # Collapse multiple spaces and strip
    title = re.sub(r"\s+", " ", title).strip()

    logger.info(f"EXTRACTED TITLE: {title}")
    return title


def extract_season(text):
    """
    Extract season number from text.
    Examples: S01 → 1, Season 2 → 2
    """
    if not text:
        return None

    match = re.search(r"(?:S|Season\s*)(\d+)", str(text), re.I)
    if match:
        return int(match.group(1))
    return None


def extract_quality(text):
    """
    Extract video quality (e.g., '1080p').
    Returns 'Unknown' if not found.
    """
    if not text:
        return "Unknown"

    text = str(text).lower()
    for q in ("2160p", "1440p", "1080p", "720p", "480p"):
        if q in text:
            return q
    return "Unknown"


def extract_language(text):
    """
    Extract audio language information.
    Returns 'Dual Audio', 'Hindi', 'English', or empty string.
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


def extract_year(text):
    match = re.search(
        r"(19\d{2}|20\d{2})",
        text,
    )
    return int(match.group()) if match else None


def has_metadata(text):
    """Return True if the text contains any of the metadata patterns."""
    return bool(_METADATA_RE.search(str(text)))

