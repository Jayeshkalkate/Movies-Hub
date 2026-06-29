# movie_parser.py
import re
import unicodedata
import logging
from typing import Optional, List, Tuple, Dict

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# 1. CONSTANTS – lists of noise to remove
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

# Codecs (video, audio, container) – expanded
CODEC_PATTERN = re.compile(
    r"\b(x264|x265|HEVC|H\.?264|H\.?265|AVC|MP4|MKV|AVI|"
    r"DDP\s*5\s*\.?\s*1|DDP|Opus|AV1|AAC|AC3|EAC3|DTS)\b",
    re.IGNORECASE,
)

# Format tags, release groups, and other noise (extensive list)
# -------------------------------------------------------------------
# 1. CONSTANTS – lists of noise to remove
# -------------------------------------------------------------------

# ... (previous patterns remain the same) ...

# Format tags, release groups, and other noise (extensive list)
NOISE_TAGS = [
    # Source
    "WEB-DL", "WEBRip", "WEBHD", "HDRip", "BluRay", "BRRip",
    "BDRip", "DVDRip", "HDTS", "HDTC", "HDCAM", "CAMRip",
    "CAM", "HC", "Remux",
    # Resolution / colour
    "10Bit", "8Bit", "HDR", "HDR10", "HDR10+",
    # Codec names (already in CODEC_PATTERN, but adding explicit)
    "x264", "x265", "HEVC", "H.264", "H.265", "AVC",
    "AV1", "Opus", "AAC", "AC3", "EAC3", "DTS",
    # Audio flags
    "DDP5.1", "DDP", "DD5.1", "TrueHD", "Atmos", "Dolby",
    "2CH", "5.1",
    # Language flags
    "Dual Audio", "Multi Audio", "MultiAudio", "ORG",
    "Dubbed", "ESub", "ESubs", "MSubs",
    # Service / platform
    "AMZN", "NF", "DSNP", "COMBINED", "CR",
    # Release groups (common)
    "GOGETA", "NeoNyx343", "SiN", "L0E", "RARBG",
    "GalaxyRG", "YTS", "PSA", "AM", "Immortal", "Godfather",
    "JohnWick",         # user reported
    "RIP",              # user reported
    # Other
    "Complete", "Series",
    # Removed: "UNCUT", "EXTENDED", "REMASTERED" – they are version info and should be preserved
    "PROPER", "REPACK",
    "WEB DL",  # with space
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
# 2. KOREAN DRAMA DETECTION (helper for detector)
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
    """Heuristic to detect Korean dramas based on keywords."""
    if not title:
        return False
    lower = title.lower()
    for kw in KOREAN_DRAMA_KEYWORDS:
        if kw in lower:
            return True
    return False

# -------------------------------------------------------------------
# 3. CLEANING FUNCTION (core)
# -------------------------------------------------------------------

def clean_text(text: str) -> str:
    """
    Remove all unwanted tokens: emojis, fancy Unicode, URLs, mentions,
    hashtags, file sizes, bitrates, codecs, and all NOISE_TAGS.
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
    """
    Extract season and episode numbers.
    Returns (season, episode) – either can be None.
    """
    if not text:
        return None, None

    # Try compact S01E05
    match = SEASON_EP_COMPACT.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Try Season X Episode Y
    match = SEASON_EP_WORDS.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Try generic S/E pattern
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
    # Return the best (by numeric resolution)
    def parse_res(q: str) -> int:
        q_lower = q.lower()
        if q_lower == "4k":
            return 2160
        if q_lower.endswith("p"):
            return int(q_lower[:-1])
        return 0
    return max(matches, key=parse_res)

def extract_languages(text: str) -> Optional[List[str]]:
    """Extract language names from text (returns lowercase list)."""
    if not text:
        return None
    found = set()
    # Detect multi/dual audio phrases
    if re.search(r"\b(?:multi|dual)\s+audio\b", text, re.IGNORECASE):
        found.add("multi audio")
    for lang in LANGUAGE_SET:
        if lang in ("multi audio", "dual audio", "multi", "dual"):
            continue
        if re.search(rf"\b{re.escape(lang)}\b", text, re.IGNORECASE):
            found.add(lang.lower())
    return list(found) if found else None

# -------------------------------------------------------------------
# 5. MAIN PARSER – focus on the first meaningful line
# -------------------------------------------------------------------

def parse_movie(text: str) -> Dict[str, any]:
    """
    Parse a movie caption/filename and return a dictionary with:
        title (str),
        year (int or None),
        season (int or None),
        episode (int or None),
        quality (str or None),
        languages (list[str] or None)
    """
    if not text:
        return {
            "title": "",
            "year": None,
            "season": None,
            "episode": None,
            "quality": None,
            "languages": None,
        }

    # Split into lines and take the first non-empty line as the primary source
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {
            "title": "",
            "year": None,
            "season": None,
            "episode": None,
            "quality": None,
            "languages": None,
        }

    primary_line = lines[0]  # use the first line

    # Step 1: clean the primary line (remove all noise)
    cleaned = clean_text(primary_line)

    # If after cleaning the line becomes empty, try the next lines
    if not cleaned and len(lines) > 1:
        # Possibly the first line was only noise, use second line
        cleaned = clean_text(lines[1])

    # If still empty, fallback to whole text cleaning (but try to avoid)
    if not cleaned:
        cleaned = clean_text(text)

    # Step 2: extract metadata (the order matters: we remove after extracting)
    year = extract_year(cleaned)
    if year is not None:
        cleaned = re.sub(rf"\(?\b{year}\b\)?", "", cleaned)   # remove year

    season, episode = extract_season_episode(cleaned)
    # Remove any season/episode patterns completely (including multiple episodes)
    cleaned = re.sub(r'\b[Ss]\d+\b', '', cleaned)      # removes S01, S1, etc.
    cleaned = re.sub(r'\b[Ee]\d+\b', '', cleaned)      # removes E01, E1, etc.
    # Also remove combined S01E01 patterns if any remained
    cleaned = re.sub(r'(?i)s\d+e\d+', '', cleaned)

    quality = extract_quality(cleaned)
    if quality is not None:
        cleaned = re.sub(rf"\b{re.escape(quality)}\b", "", cleaned, flags=re.IGNORECASE)

    languages = extract_languages(cleaned)
    if languages is not None:
        for lang in languages:
            cleaned = re.sub(rf"\b{re.escape(lang)}\b", "", cleaned, flags=re.IGNORECASE)

    # Step 3: the remainder is the title
    # Remove leftover separators and collapse spaces
    cleaned = re.sub(r"\s*[~+|/]\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    title = cleaned if cleaned else None

    # Additional check: if title is None but we had a primary line, use that (but cleaned)
    if not title and primary_line:
        # attempt to clean more aggressively: remove year, season, etc.
        # But we already did that; maybe the line was all noise.
        # Fallback: take the primary line and strip common prefixes
        fallback = primary_line
        # Remove any parenthesized content that might be metadata
        fallback = re.sub(r"\([^)]*\)", "", fallback)
        fallback = re.sub(r"\[[^)]*\]", "", fallback)
        fallback = re.sub(r"\{[^)]*\}", "", fallback)
        fallback = re.sub(r"\s+", " ", fallback).strip()
        if fallback:
            title = fallback

    return {
        "title": title,
        "year": year,
        "season": season,
        "episode": episode,
        "quality": quality,
        "languages": languages,
        "is_korean_drama": is_likely_korean_drama(title) if title else False,
    }

# -------------------------------------------------------------------
# 6. BACKWARD-COMPATIBLE WRAPPERS (optional)
# -------------------------------------------------------------------

def extract_title(text: str) -> str:
    """Return just the cleaned title."""
    return parse_movie(text).get("title", "")

def extract_season(text: str) -> Optional[int]:
    """Return season number (or None)."""
    return parse_movie(text).get("season")

def extract_episode(text: str) -> Optional[int]:
    """Return episode number (or None)."""
    return parse_movie(text).get("episode")

def clean_caption(text: str) -> str:
    """Legacy: remove join, @, t.me – now handled by clean_text."""
    if not text:
        return ""
    text = re.sub(r"(?i)\bjoin\b.*", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"t\.me/\S+", "", text)
    return text.strip()

# -------------------------------------------------------------------
# 7. EXAMPLE USAGE
# -------------------------------------------------------------------

if __name__ == "__main__":
    test_cases = [
        "Paatal Lok 2020 S01 COMBINED AMZN WEB DL",
        "Pirates Of The Caribbean Dead Men Tell No Tales 2017 720p 10Bit English Hindi mkv",
        "File name:- Inception 2010 720p HDRip",
        "Spider-Man.No.Way.Home.2021.2160p.WEB-DL",
        "𝙁𝙞𝙡𝙚 𝙣𝙖𝙢𝙚:- Avatar The Way of Water 2022 1080p",
        "Weak Hero Class 1 (2022) S01 1080p WEB-DL x265 DDP 5.1",
        "Join @MoviesHub\nPushpa 2 (2024) 1080p Hindi",
        "Spider Man Across the Spider Verse RIP AV1 Opus Msubs JohnWick NeoNyx343",
        "The Last of Us S01 E01 E04 COMBINED",
    ]

    for cap in test_cases:
        result = parse_movie(cap)
        print(f"Input: {cap[:60]}...")
        print(f"  -> {result}\n")