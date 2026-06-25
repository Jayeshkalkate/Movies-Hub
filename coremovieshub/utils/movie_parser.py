import re
import logging
import unicodedata

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# 1. COMBINED PATTERN – all metadata in one regex
#    (case‑insensitive, compiled once for performance)
# -------------------------------------------------------------------
METADATA_PATTERNS = [
    # ─── Resolution ────────────────────────────────────────────────
    r"\b2160p\b", r"\b1440p\b", r"\b1080p\b", r"\b720p\b", r"\b480p\b",

    # ─── Source / Rip type ────────────────────────────────────────
    r"\bWEB[- ]DL\b", r"\bWEBRip\b", r"\bBluRay\b", r"\bHDRip\b", r"\bDVDRip\b",
    r"\bCAM\b", r"\bHDTC\b", r"\bHC\b", r"\bWEB\b", r"\bWEBHD\b",
    r"\bBRRip\b", r"\bBDRip\b", r"\bBlu-Ray\b",          # added

    # ─── Languages ────────────────────────────────────────────────
    r"\bHindi\b", r"\bEnglish\b", r"\bTamil\b", r"\bTelugu\b", r"\bMalayalam\b",

    # ─── Audio / Subtitle flags ──────────────────────────────────
    r"\bDual Audio\b", r"\bORG\b", r"\bDubbed\b", r"\bESub\b", r"\bESubs?\b",

    # ─── Codec & bit depth ────────────────────────────────────────
    r"\b10bit\b", r"\bHEVC\b", r"\bAAC\b", r"\bDDP\b",
    r"\bH264\b", r"\bH265\b",                                 # added
    r"\bHE\b",                                                # often used for HEVC

    # ─── Video codec (old style) ─────────────────────────────────
    r"\bx264\b", r"\bx265\b",

    # ─── Audio channels ───────────────────────────────────────────
    r"\b2CH\b", r"\b5\.1\b",

    # ─── Release groups ──────────────────────────────────────────
    r"\bPSA\b", r"\bImmortal\b", r"\bGodfather\b", r"\bYTS\b", r"\bAM\b",

    # ─── File extensions ─────────────────────────────────────────
    r"\bmkv\b", r"\bmp4\b", r"\bavi\b",

    # ─── Spam / promotions ───────────────────────────────────────
    r"JOIN\s+@\w+",
    r"\bor\b",                                                # standalone "or"

    # ─── Season / Episode / Part ─────────────────────────────────
    r"\bSeason\s*\d+\b", r"\bS\d+\b",
    r"\bEpisode\s*\d+\b", r"\bE\d+\b",
    r"\bPart\s*\d+\b",

    # ─── Miscellaneous ────────────────────────────────────────────
    r"\bComplete\b", r"\bSeries\b",
    r"\bMulti Audio\b", r"\bMultiAudio\b",

    # ─── Year (four digits) ──────────────────────────────────────
    r"\b(?:19|20)\d{2}\b",

    # ─── Additional audio codecs & formats ──────────────────────
    r"\bDD\s*\d+\s*\d+\b",          # "DD 5 1", "DD5.1", etc.
    r"\bAAC\s*\d+\s*\d+\b",         # "AAC 5.1"
    r"\bNF\b",                      # Netflix

    # ─── HDR / Dolby / DTS ──────────────────────────────────────
    r"\bHDR\b",
    r"\bHDR10\b",
    r"\bHDR10\+\b",                # escaped '+'
    r"\bDolby\b",
    r"\bAtmos\b",
    r"\bTrueHD\b",
    r"\bDTS\b",

    # ─── Edition / status flags ──────────────────────────────────
    r"\bUNCUT\b",
    r"\bEXTENDED\b",
    r"\bREMASTERED\b",
    r"\bPROPER\b",
    r"\bREPACK\b",
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