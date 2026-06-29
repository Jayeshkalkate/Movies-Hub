# movie_parser.py

"""
Movie and TV show caption/filename parser.

This module extracts structured metadata from raw text strings (captions,
filenames, titles) commonly found in media files. It handles:

- Cleaning: removal of noise (codecs, release groups, sizes, URLs, etc.)
- Extraction: title, year, season, episode, quality, languages.
- Korean drama detection (optional).
- Robust preprocessing for various input formats.

All functions are pure (no external dependencies except standard library).
"""

import re
import unicodedata
import logging
from typing import Optional, List, Tuple, Dict, Any, Set

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# 1. CONSTANTS – lists of noise to remove (expanded)
# -------------------------------------------------------------------

# Emojis and fancy symbols
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
    "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)
FANCY_CHARS_PATTERN = re.compile(
    r"[\U0001D400-\U0001D7FF\U0001F150-\U0001F19A]",
    flags=re.UNICODE,
)

# URLs, mentions, hashtags
URL_PATTERN = re.compile(r"https?://\S+|t\.me/\S+", re.IGNORECASE)
MENTION_PATTERN = re.compile(r"@\S+")
HASHTAG_PATTERN = re.compile(r"#\S+")

# Sizes, bitrates
FILESIZE_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*(GB|MB|KB|TB)\b", re.IGNORECASE)
BITRATE_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*(Kbps|Mbps)\b", re.IGNORECASE)

# Codecs (video, audio, container) – expanded with common variants
CODEC_PATTERN = re.compile(
    r"\b(x264|x265|HEVC|H\.?264|H\.?265|AVC|MP4|MKV|AVI|"
    r"DDP\s*5\s*\.?\s*1|DDP|Opus|AV1|AAC|AC3|EAC3|DTS|"
    r"MPEG|DivX|XviD|WMV|FLV|WEBM|M4V|M2TS|TS)\b",
    re.IGNORECASE,
)

# Format tags, release groups, and other noise – massively expanded
NOISE_TAGS = [
    # Source
    "WEB-DL", "WEBRip", "WEBHD", "HDRip", "BluRay", "BRRip",
    "BDRip", "DVDRip", "HDTS", "HDTC", "HDCAM", "CAMRip",
    "CAM", "HC", "Remux", "BDMV", "WEB DL",  # with space
    # Resolution / colour
    "10Bit", "8Bit", "HDR", "HDR10", "HDR10+", "DolbyVision",
    # Codec names (already in CODEC_PATTERN, but explicit)
    "x264", "x265", "HEVC", "H.264", "H.265", "AVC",
    "AV1", "Opus", "AAC", "AC3", "EAC3", "DTS",
    # Audio flags
    "DDP5.1", "DDP", "DD5.1", "TrueHD", "Atmos", "Dolby",
    "2CH", "5.1", "7.1", "6CH", "8CH",
    # Language flags
    "Dual Audio", "Multi Audio", "MultiAudio", "ORG",
    "Dubbed", "ESub", "ESubs", "MSubs", "Subs", "Subbed",
    # Service / platform
    "AMZN", "NF", "DSNP", "COMBINED", "CR", "HMAX", "HBO", "AppleTV",
    # Release groups (common)
    "GOGETA", "NeoNyx343", "SiN", "L0E", "RARBG",
    "GalaxyRG", "YTS", "PSA", "AM", "Immortal", "Godfather",
    "JohnWick", "RIP", "EVO", "NTG", "MkvCage", "MkvKing",
    "AniDL", "SubsPlease", "Erai-raws", "ASAP", "Xclusive",
    "Kings", "Bone", "Telly", "HDTV", "MIRCrew", "iNTENSO",
    "FGT", "SiGMA", "KiNGDOM", "SPARKS", "DIMENSION", "ETHiCS",
    "ViSiON", "iON", "LiNE", "NGB", "ORPHEUS", "LiBRARiANS",
    "Chameleon", "SVA", "MZABI", "HANDJOB", "BATV", "D-Z0N3",
    "Framestor", "ESiR", "CtrlHD", "DON", "HiDt", "PTP",
    "CRiSC", "iMAGiNE", "ROAR", "WAR", "MZ",
    # Other common
    "Complete", "Series", "PROPER", "REPACK", "INTERNAL",
    # User-suggested additions
    "cleaned", "s print", "hq print", "hd print", "print",
    "themoviesboss", "vegamovies", "worldfree4u", "hdhub4u",
    "mkv", "mp4", "avi", "mov", "wmv", "flv", "webm", "m4v", "m2ts",
    "hdcam", "hq", "hevc", "avc", "aac", "ac3", "eac3", "dts",
    "ddp", "ddp5.1", "5.1", "2ch", "7.1",
    "english", "hindi", "tamil", "telugu", "malayalam", "kannada",
    "bengali", "marathi", "gujarati", "punjabi", "urdu",
    "spanish", "french", "german", "chinese", "japanese", "korean",
    "russian", "arabic", "portuguese", "indonesian", "thai",
    "vietnamese", "dual", "multi", "org", "dubbed", "subs",
    "web", "bluray", "bdrip", "brrip", "dvdrip", "hdtc", "hdcam",
    "camrip", "cam", "hc", "remux",
    "10bit", "8bit", "hdr", "hdr10", "dolbyvision",
    "proper", "repack", "internal", "complete", "series",
    # Additional scene groups
    "ROCCaT", "ViSION", "iNTERNAL", "iNT", "PROPER",
    "REPACK", "REMUX", "RERIP", "RETAIL", "VOD",
    "AMZN", "NF", "DSNP", "HMAX", "HBO", "AppleTV+",
    # More generic
    "WEBRip", "WEBDL", "BluRay", "BDRip", "DVDRip",
]

# Year pattern (captures 4-digit year)
YEAR_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")

# Season/Episode patterns
SEASON_EP_COMPACT = re.compile(r"(?i)s(\d{1,2})e(\d{1,2})")
SEASON_EP_WORDS = re.compile(r"(?i)season\s*(\d{1,2})\s+episode\s*(\d{1,2})")
SEASON_EP_PATTERN = re.compile(
    r"(?i)(?:s|season)\s*(\d{1,2})\s*(?:e|episode)?\s*(\d{1,2})?"
)

# Quality patterns
QUALITY_PATTERN = re.compile(r"\b(\d{3,4}p|4k|2160p|1080p|720p|480p|360p)\b", re.IGNORECASE)

# Language names (for extraction)
LANGUAGE_SET = {
    "hindi", "telugu", "tamil", "malayalam", "kannada",
    "bengali", "marathi", "gujarati", "punjabi", "urdu",
    "english", "spanish", "french", "german", "chinese",
    "japanese", "korean", "russian", "arabic", "portuguese",
    "indonesian", "thai", "vietnamese",
    "multi audio", "dual audio", "multi", "dual",
}


# -------------------------------------------------------------------
# 2. KOREAN DRAMA DETECTION (unchanged)
# -------------------------------------------------------------------

KOREAN_DRAMA_KEYWORDS = {
    "weak hero", "class", "signal", "stranger", "crash landing", "reply",
    "hospital playlist", "prison playbook", "it's okay to not be okay",
    "vincenzo", "descendants of the sun", "goblin", "guardian", "mr. sunshine",
    "kingdom", "sweet home", "hellbound", "all of us are dead",
    "squid game", "the glory", "the penthouse", "mouse", "beyond evil",
    "flower of evil", "the devil judge", "taxi driver", "the veil",
    "through the darkness", "the king's affection", "red sleeve",
    "the cursed", "possessed", "the guest", "save me", "strangers from hell",
    "the uncanny counter", "awaken", "night in paradise", "be melodramatic",
    "because this is my first life", "misaeng", "my mister", "mother",
}


def is_likely_korean_drama(title: str) -> bool:
    """Return True if the title matches known Korean drama keywords."""
    if not title:
        return False
    lower = title.lower()
    return any(kw in lower for kw in KOREAN_DRAMA_KEYWORDS)


# -------------------------------------------------------------------
# 3. CLEANING FUNCTION (core)
# -------------------------------------------------------------------

def clean_text(text: str) -> str:
    """
    Remove all unwanted tokens: emojis, fancy Unicode, URLs, mentions,
    hashtags, file sizes, bitrates, codecs, and all NOISE_TAGS.

    Args:
        text: Input string.

    Returns:
        Cleaned string with noise removed.
    """
    if not text:
        return ""

    # Normalize fancy Unicode to ASCII equivalents
    text = unicodedata.normalize('NFKC', text)
    # Remove emojis and other symbol blocks
    text = EMOJI_PATTERN.sub("", text)
    text = FANCY_CHARS_PATTERN.sub("", text)
    # Remove URLs, mentions, hashtags
    text = URL_PATTERN.sub("", text)
    text = MENTION_PATTERN.sub("", text)
    text = HASHTAG_PATTERN.sub("", text)
    # Remove file sizes and bitrates
    text = FILESIZE_PATTERN.sub("", text)
    text = BITRATE_PATTERN.sub("", text)
    # Remove codecs (video/audio/container)
    text = CODEC_PATTERN.sub("", text)
    # Remove all noise tags (case‑insensitive, word boundaries)
    for tag in NOISE_TAGS:
        # For multi‑word tags, escape and use word boundaries
        text = re.sub(rf"\b{re.escape(tag)}\b", "", text, flags=re.IGNORECASE)
    # Remove leftover separators like '~', '+', '|', etc.
    text = re.sub(r"\s*[~+|/]\s*", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


# -------------------------------------------------------------------
# 4. EXTRACTION FUNCTIONS
# -------------------------------------------------------------------

def extract_year(text: str) -> Optional[int]:
    """Extract a 4-digit year (1900–2099) from text."""
    if not text:
        return None
    match = YEAR_PATTERN.search(text)
    if match:
        return int(match.group(1))
    return None


def extract_season_episode(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract season and episode numbers."""
    if not text:
        return None, None
    match = SEASON_EP_COMPACT.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = SEASON_EP_WORDS.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = SEASON_EP_PATTERN.search(text)
    if match:
        season = int(match.group(1)) if match.group(1) else None
        episode = int(match.group(2)) if match.group(2) else None
        return season, episode
    return None, None


def extract_quality(text: str) -> Optional[str]:
    """Extract the highest quality (e.g., '1080p', '4K') from text."""
    if not text:
        return None
    matches = QUALITY_PATTERN.findall(text)
    if not matches:
        return None

    def parse_res(q: str) -> int:
        q_lower = q.lower()
        if q_lower == "4k":
            return 2160
        if q_lower.endswith("p"):
            try:
                return int(q_lower[:-1])
            except ValueError:
                return 0
        return 0

    return max(matches, key=parse_res)


def extract_languages(text: str) -> Optional[List[str]]:
    """Extract language names from text (returns lowercase list)."""
    if not text:
        return None
    found: Set[str] = set()
    # Check for multi/dual audio
    if re.search(r"\b(?:multi|dual)\s+audio\b", text, re.IGNORECASE):
        found.add("multi audio")
    for lang in LANGUAGE_SET:
        if lang in ("multi audio", "dual audio", "multi", "dual"):
            continue
        if re.search(rf"\b{re.escape(lang)}\b", text, re.IGNORECASE):
            found.add(lang.lower())
    return list(found) if found else None


# -------------------------------------------------------------------
# 5. MAIN PARSER – enhanced with robust preprocessing
# -------------------------------------------------------------------

def parse_movie(text: str) -> Dict[str, Any]:
    """
    Parse a movie caption/filename and return a dictionary with:
        title (str),
        year (int or None),
        season (int or None),
        episode (int or None),
        quality (str or None),
        languages (list[str] or None),
        is_korean_drama (bool).

    The function performs a series of cleaning and extraction steps
    to produce the most accurate metadata possible.

    Args:
        text: Raw input string.

    Returns:
        Dict with keys: title, year, season, episode, quality, languages, is_korean_drama.
    """
    if not text:
        return {
            "title": "",
            "year": None,
            "season": None,
            "episode": None,
            "quality": None,
            "languages": None,
            "is_korean_drama": False,
        }

    # ----- STEP 1: Normalize raw input -----
    raw = text
    # Replace common separators with spaces
    raw = raw.replace("_", " ").replace(".", " ").replace("-", " ")
    # Remove file extensions
    raw = re.sub(r"\.(mkv|mp4|avi|mov|wmv|flv|webm|m4v|m2ts)$", "", raw, flags=re.IGNORECASE)
    # Remove common prefixes like "File name:-"
    raw = re.sub(r"^file\s*name\s*[:=-]\s*", "", raw, flags=re.IGNORECASE)
    # Remove "Join @..." messages
    raw = re.sub(r"(?i)join\s*@\S+", "", raw)
    raw = re.sub(r"(?i)\bjoin\b.*", "", raw)
    # Collapse multiple spaces
    raw = re.sub(r"\s+", " ", raw).strip()

    # ----- STEP 2: Truncate after the last 4-digit year -----
    year_matches = list(re.finditer(r"\b(19|20)\d{2}\b", raw))
    if year_matches:
        last_year = year_matches[-1]
        # Keep everything up to and including that year
        raw = raw[:last_year.end()]

    # Now use this normalized text as the primary input
    text = raw

    # ----- STEP 3: Split into lines and take the first non-empty line -----
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {
            "title": "",
            "year": None,
            "season": None,
            "episode": None,
            "quality": None,
            "languages": None,
            "is_korean_drama": False,
        }

    primary_line = lines[0]

    # ----- STEP 4: Clean the primary line (remove noise) -----
    cleaned = clean_text(primary_line)

    # If cleaning emptied the line, try the next line
    if not cleaned and len(lines) > 1:
        cleaned = clean_text(lines[1])

    # If still empty, fallback to whole text cleaning
    if not cleaned:
        cleaned = clean_text(text)

    # ----- STEP 5: Extract metadata (order matters) -----
    year = extract_year(cleaned)
    if year is not None:
        cleaned = re.sub(rf"\(?\b{year}\b\)?", "", cleaned)

    season, episode = extract_season_episode(cleaned)
    # Remove season/episode patterns
    cleaned = re.sub(r'\b[Ss]\d+\b', '', cleaned)
    cleaned = re.sub(r'\b[Ee]\d+\b', '', cleaned)
    cleaned = re.sub(r'(?i)s\d+e\d+', '', cleaned)

    quality = extract_quality(cleaned)
    if quality is not None:
        cleaned = re.sub(rf"\b{re.escape(quality)}\b", "", cleaned, flags=re.IGNORECASE)

    languages = extract_languages(cleaned)
    if languages is not None:
        for lang in languages:
            cleaned = re.sub(rf"\b{re.escape(lang)}\b", "", cleaned, flags=re.IGNORECASE)

    # ----- STEP 6: The remainder is the title -----
    # Remove leftover separators and collapse spaces
    cleaned = re.sub(r"\s*[~+|/]\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    title = cleaned if cleaned else None

    # Fallback: if title is empty, strip bracketed content aggressively
    if not title and primary_line:
        fallback = primary_line
        # Remove parenthesized/bracketed content
        fallback = re.sub(r"\([^)]*\)", "", fallback)
        fallback = re.sub(r"\[[^)]*\]", "", fallback)
        fallback = re.sub(r"\{[^)]*\}", "", fallback)
        fallback = re.sub(r"\s+", " ", fallback).strip()
        if fallback:
            title = fallback

    # Final title cleanup
    if title:
        # Remove leading/trailing separators
        title = re.sub(r"^[\s\-_]+|[\s\-_]+$", "", title)
        # Capitalize each word (optional, but keep as is)
        # title = title.title()  # Uncomment if needed

    return {
        "title": title or "",
        "year": year,
        "season": season,
        "episode": episode,
        "quality": quality,
        "languages": languages,
        "is_korean_drama": is_likely_korean_drama(title) if title else False,
    }


# -------------------------------------------------------------------
# 6. BACKWARD-COMPATIBLE WRAPPERS
# -------------------------------------------------------------------

def extract_title(text: str) -> str:
    """Return the extracted title from text."""
    return parse_movie(text).get("title", "")


def extract_season(text: str) -> Optional[int]:
    """Return extracted season number."""
    return parse_movie(text).get("season")


def extract_episode(text: str) -> Optional[int]:
    """Return extracted episode number."""
    return parse_movie(text).get("episode")


def clean_caption(text: str) -> str:
    """Quick cleaning for captions (remove join messages, mentions)."""
    if not text:
        return ""
    text = re.sub(r"(?i)\bjoin\b.*", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"t\.me/\S+", "", text)
    return text.strip()


# -------------------------------------------------------------------
# 7. BATCH PROCESSING
# -------------------------------------------------------------------

def parse_many(texts: List[str]) -> List[Dict[str, Any]]:
    """Parse a list of captions and return a list of result dicts."""
    return [parse_movie(t) for t in texts]


# -------------------------------------------------------------------
# 8. EXAMPLE USAGE & TEST
# -------------------------------------------------------------------

if __name__ == "__main__":
    test_cases = [
        "One_Piece_Film_Red_2022_Hindi_Cleaned_1080p_S_Print_x264_AAC_themoviesboss.mkv",
        "Paatal Lok 2020 S01 COMBINED AMZN WEB DL",
        "Pirates Of The Caribbean Dead Men Tell No Tales 2017 720p 10Bit English Hindi mkv",
        "File name:- Inception 2010 720p HDRip",
        "Spider-Man.No.Way.Home.2021.2160p.WEB-DL",
        "𝙁𝙞𝙡𝙚 𝙣𝙖𝙢𝙚:- Avatar The Way of Water 2022 1080p",
        "Weak Hero Class 1 (2022) S01 1080p WEB-DL x265 DDP 5.1",
        "Join @MoviesHub\nPushpa 2 (2024) 1080p Hindi",
        "Spider Man Across the Spider Verse RIP AV1 Opus Msubs JohnWick NeoNyx343",
        "The Last of Us S01 E01 E04 COMBINED",
        "One_Piece_Film_Red_2022_Hindi_Cleaned_1080p_S_Print_x264_AAC_themoviesboss",
        "Kingdom (2019) S02 1080p NF WEB-DL DDP5.1 x264",
        "Stranger Things S04E01 4K HDR",
        "The Dark Knight 2008 1080p BluRay x264",
    ]

    for cap in test_cases:
        result = parse_movie(cap)
        print(f"Input: {cap[:80]}...")
        print(f"  -> {result}\n")
        
