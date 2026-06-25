import re
import logging
import unicodedata

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# 1. COMBINED PATTERN – all metadata in one regex
#    (case‑insensitive, compiled once for performance)
# -------------------------------------------------------------------
METADATA_PATTERNS = [

    # Resolution
    r"\b2160p\b",
    r"\b1440p\b",
    r"\b1080p\b",
    r"\b720p\b",
    r"\b480p\b",

    # Source
    r"\bWEB[- ]?DL\b",
    r"\bWEBRip\b",
    r"\bWEBHD\b",
    r"\bHDRip\b",
    r"\bBlu[- ]?Ray\b",
    r"\bBRRip\b",
    r"\bBDRip\b",
    r"\bDVDRip\b",
    r"\bHDTS\b",
    r"\bHDTC\b",
    r"\bHDCAM\b",
    r"\bCAMRip\b",
    r"\bCAM\b",
    r"\bHC\b",

    # Codecs
    r"\bx264\b",
    r"\bx265\b",
    r"\bH264\b",
    r"\bH265\b",
    r"\bHEVC\b",
    r"\bHE\b",

    # Audio
    r"\bAAC\b",
    r"\bDDP\b",
    r"\bDD5\.1\b",
    r"\b5\.1\b",
    r"\b2CH\b",
    r"\bTrueHD\b",
    r"\bAtmos\b",
    r"\bDolby\b",
    r"\bDTS\b",

    # HDR
    r"\bHDR\b",
    r"\bHDR10\b",
    r"\bHDR10\+\b",

    # Languages
    r"\bHindi\b",
    r"\bEnglish\b",
    r"\bTamil\b",
    r"\bTelugu\b",
    r"\bMalayalam\b",
    r"\bKannada\b",
    r"\bMarathi\b",
    r"\bPunjabi\b",
    r"\bBengali\b",

    # Audio flags
    r"\bDual Audio\b",
    r"\bMulti Audio\b",
    r"\bMultiAudio\b",
    r"\bORG\b",
    r"\bDubbed\b",
    r"\bESub\b",
    r"\bESubs\b",

    # Misc
    r"\bComplete\b",
    r"\bSeries\b",
    r"\bUNCUT\b",
    r"\bEXTENDED\b",
    r"\bREMASTERED\b",
    r"\bPROPER\b",
    r"\bREPACK\b",
    r"\bNF\b",

    # Release Groups
    r"\bPSA\b",
    r"\bYTS\b",
    r"\bAM\b",
    r"\bImmortal\b",
    r"\bGodfather\b",

    # File extensions
    r"\bmkv\b",
    r"\bmp4\b",
    r"\bavi\b",

    # Season / Episode
    r"\bSeason\s*\d+\b",
    r"\bS\d+\b",
    r"\bEpisode\s*\d+\b",
    r"\bE\d+\b",

    # Year
    r"\b(?:19|20)\d{2}\b",

    # Spam
    r"JOIN\s+@\w+",
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
    Extract a clean movie title from Telegram captions or filenames.

    Examples:
    ---------------------------------------------------------
    File name:- Inception 2010 720p HDRip
        -> Inception

    Inception.2010.1080p.BluRay.x264
        -> Inception

    Spider-Man.No.Way.Home.2021.2160p.WEB-DL
        -> Spider Man No Way Home

    𝙁𝙞𝙡𝙚 𝙣𝙖𝙢𝙚:- Avatar The Way of Water 2022 1080p
        -> Avatar The Way of Water
    """

    if not text:
        return ""

    title = str(text)

    # -------------------------------------------------
    # Normalize Unicode
    # -------------------------------------------------

    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode()

    # -------------------------------------------------
    # Keep only first line
    # -------------------------------------------------

    title = title.splitlines()[0]

    # -------------------------------------------------
    # Replace common separators
    # -------------------------------------------------

    title = re.sub(r"[._+]", " ", title)

    # Replace multiple hyphens with space
    title = re.sub(r"-{2,}", " ", title)

    # -------------------------------------------------
    # Remove common prefixes
    # -------------------------------------------------

    title = re.sub(
        r"(?i)\b(file\s*name|filename|movie\s*name|title)\b\s*[:-]*\s*",
        "",
        title,
    )

    # -------------------------------------------------
    # Remove Telegram usernames
    # -------------------------------------------------

    title = re.sub(r"@\w+", "", title)

    # -------------------------------------------------
    # Remove URLs
    # -------------------------------------------------

    title = re.sub(r"https?://\S+", "", title)
    title = re.sub(r"t\.me/\S+", "", title)

    # -------------------------------------------------
    # Remove metadata
    # -------------------------------------------------

    title = _METADATA_RE.sub("", title)
    
    
    # -------------------------------------------------
    # Remove leftover junk words
    # -------------------------------------------------
    
    title = re.sub(
        r"\b(HDTS|HDTC|HDCAM|CAMRip|CAM|WEB|WEBRip|WEBDL|BluRay|HDRip|AAC|x264|x265|HEVC|HC|ESub|Hindi|English|Tamil|Telugu|Malayalam|Kannada|Marathi|Punjabi|Bengali)\b",
        "",
        title,
        flags=re.IGNORECASE,
    )

    # -------------------------------------------------
    # Remove empty brackets
    # -------------------------------------------------

    title = re.sub(r"\(\s*\)", "", title)
    title = re.sub(r"\[\s*\]", "", title)
    title = re.sub(r"\{\s*\}", "", title)

    # -------------------------------------------------
    # Remove remaining brackets
    # -------------------------------------------------

    title = re.sub(r"[\[\](){}]", "", title)

    # -------------------------------------------------
    # Remove extra punctuation
    # -------------------------------------------------

    title = re.sub(r"[|]", " ", title)
    title = re.sub(r"\s*:\s*", " ", title)
    title = re.sub(r"\s*;\s*", " ", title)
    title = re.sub(r"\s*,\s*", " ", title)

    # -------------------------------------------------
    # Collapse spaces
    # -------------------------------------------------

    title = re.sub(r"\s+", " ", title)

    # -------------------------------------------------
    # Trim unwanted characters
    # -------------------------------------------------

    title = title.strip(" -_.|")

    logger.info("Extracted title: %s", title)

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
    if not text:
        return ""

    lower = str(text).lower()

    if "dual audio" in lower:
        return "Dual Audio"

    languages = [
        "Hindi",
        "English",
        "Tamil",
        "Telugu",
        "Malayalam",
        "Kannada",
        "Marathi",
        "Punjabi",
        "Bengali",
    ]

    for lang in languages:
        if lang.lower() in lower:
            return lang

    return ""


def extract_year(text):
    """
    Extract a 4-digit year (1900–2099) from the text.
    Returns int or None.
    """
    if not text:
        return None
    match = re.search(r"(19\d{2}|20\d{2})", str(text))
    return int(match.group()) if match else None


def has_metadata(text):
    """Return True if the text contains any of the metadata patterns."""
    return bool(_METADATA_RE.search(str(text)))