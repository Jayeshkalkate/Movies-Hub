import re
from dataclasses import dataclass
from typing import Optional, List, Tuple

# ------------------- Constant Patterns and Sets -------------------

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

URL_PATTERN = re.compile(r"https?://\S+|t\.me/\S+", re.IGNORECASE)
MENTION_PATTERN = re.compile(r"@\S+")
HASHTAG_PATTERN = re.compile(r"#\S+")
FILESIZE_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*(GB|MB|KB|TB)\b", re.IGNORECASE)

CODEC_PATTERN = re.compile(
    r"\b(x264|x265|HEVC|H\.?264|H\.?265|AVC|MP4|MKV|AVI)\b", re.IGNORECASE
)

# Common format / source tags to remove from title
FORMAT_TAGS = [
    "WEB-DL",
    "WEBRip",
    "BluRay",
    "BDRip",
    "HDRip",
    "DVDRip",
    "HDTV",
    "HDrip",
    "BRrip",
    "WEB",
    "DL",
    "Rip",
    "Remux",
    "x264",
    "x265",
    "HEVC",
    "H.264",
    "H.265",
    "AVC",
]

# Fixed: captures the full 4-digit year
YEAR_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")

SEASON_EP_PATTERN = re.compile(
    r"(?i)(?:s|season)\s*(\d{1,2})\s*(?:e|episode)?\s*(\d{1,2})?"
)
# Also catch S01E05 style
SEASON_EP_COMPACT = re.compile(r"(?i)s(\d{1,2})e(\d{1,2})")
# Catch Season 1 Episode 5 (without numbers)
SEASON_EP_WORDS = re.compile(r"(?i)season\s*(\d{1,2})\s+episode\s*(\d{1,2})")

QUALITY_PATTERN = re.compile(
    r"\b(?:(\d{3,4})p|(4k)|(2160p)|(1080p)|(720p)|(480p)|(360p))\b",
    re.IGNORECASE,
)
# More specific quality patterns
QUALITY_PATTERN2 = re.compile(r"\b(\d{3,4}p|4k|2160p|1080p|720p|480p|360p)\b", re.IGNORECASE)

# Language names (add as needed)
LANGUAGE_SET = {
    "hindi",
    "telugu",
    "tamil",
    "malayalam",
    "kannada",
    "bengali",
    "marathi",
    "gujarati",
    "punjabi",
    "urdu",
    "english",
    "spanish",
    "french",
    "german",
    "chinese",
    "japanese",
    "korean",
    "russian",
    "arabic",
    "portuguese",
    "indonesian",
    "thai",
    "vietnamese",
    "multi audio",
    "dual audio",
    "multi",
    "dual",
}

# ------------------- Helper Functions -------------------

def clean_text(text: str) -> str:
    """
    Remove unwanted tokens: emojis, URLs, mentions, hashtags,
    file sizes, codecs, and common format tags.
    """
    # Remove emojis
    text = EMOJI_PATTERN.sub("", text)
    # Remove URLs, mentions, hashtags
    text = URL_PATTERN.sub("", text)
    text = MENTION_PATTERN.sub("", text)
    text = HASHTAG_PATTERN.sub("", text)
    # Remove file sizes
    text = FILESIZE_PATTERN.sub("", text)
    # Remove codecs
    text = CODEC_PATTERN.sub("", text)
    # Remove common format tags (case-insensitive)
    for tag in FORMAT_TAGS:
        text = re.sub(rf"\b{re.escape(tag)}\b", "", text, flags=re.IGNORECASE)
    # Remove extra spaces and newlines
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_year(text: str) -> Optional[int]:
    """
    Extract a 4-digit year from the text.
    Returns the year as int or None.
    """
    match = YEAR_PATTERN.search(text)
    if match:
        # group(1) holds the full year because of capturing parentheses
        return int(match.group(1))
    return None


def remove_year(text: str, year: int) -> str:
    """
    Remove the year (including surrounding parentheses) from the text.
    """
    year_str = str(year)
    # Remove patterns like (2024), 2024
    text = re.sub(rf"\(?\b{year_str}\b\)?", "", text)
    # Also remove parentheses that might be left
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_season_episode(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract season and episode numbers.
    Returns (season, episode) where either can be None.
    """
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


def remove_season_episode(text: str, season: int, episode: Optional[int]) -> str:
    """
    Remove the season/episode pattern from the text.
    """
    # Patterns to remove: S01E05, Season 1 Episode 5, S1E5, etc.
    # We can remove based on season and episode.
    season_str = str(season)
    ep_str = str(episode) if episode is not None else ""
    # Remove S01E05 style
    if episode is not None:
        text = re.sub(
            rf"(?i)s{season_str}e{ep_str}", "", text
        )  # careful: episode might be 1 digit
        text = re.sub(
            rf"(?i)s{season_str}\s*e{ep_str}", "", text
        )  # with space?
    # Remove Season X Episode Y
    if episode is not None:
        text = re.sub(
            rf"(?i)season\s*{season_str}\s+episode\s*{ep_str}", "", text
        )
    else:
        text = re.sub(rf"(?i)season\s*{season_str}", "", text)
    # Remove any leftover parentheses or extra spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_quality(text: str) -> Optional[str]:
    """
    Extract the highest quality present in the text.
    Returns quality string (e.g., "1080p", "4K") or None.
    """
    # Find all quality strings
    matches = QUALITY_PATTERN2.findall(text)
    if not matches:
        return None
    # Sort by resolution (numeric value)
    def parse_res(q: str) -> int:
        q_lower = q.lower()
        if q_lower == "4k":
            return 2160
        if q_lower.endswith("p"):
            return int(q_lower[:-1])
        return 0

    best = max(matches, key=parse_res)
    # Return in original case? We'll keep as found.
    return best


def remove_quality(text: str, quality: str) -> str:
    """
    Remove the quality string from the text.
    """
    # Remove the exact quality with word boundaries
    text = re.sub(rf"\b{re.escape(quality)}\b", "", text, flags=re.IGNORECASE)
    # Also remove surrounding separators like "|" that might be left
    text = re.sub(r"\s*\|\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_languages(text: str) -> Optional[List[str]]:
    """
    Extract language names from the text.
    Returns a list of found languages (in lowercase) or None.
    """
    found = set()
    # Detect multi/dual audio phrases first
    if re.search(r"\b(?:multi|dual)\s+audio\b", text, re.IGNORECASE):
        found.add("multi audio")
    # Then individual languages
    for lang in LANGUAGE_SET:
        # skip "multi audio" and "dual audio" as they are handled above? Actually they are already in set, but we can avoid re-adding
        if lang in ("multi audio", "dual audio", "multi", "dual"):
            continue
        # Use word boundaries to avoid partial matches
        pattern = rf"\b{re.escape(lang)}\b"
        if re.search(pattern, text, re.IGNORECASE):
            found.add(lang.lower())
    if not found:
        return None
    return list(found)


def remove_languages(text: str, languages: List[str]) -> str:
    """
    Remove language names from the text.
    """
    for lang in languages:
        # Remove "multi audio" and "dual audio" as phrases
        if lang in ("multi audio", "dual audio"):
            text = re.sub(rf"\b{re.escape(lang)}\b", "", text, flags=re.IGNORECASE)
        else:
            text = re.sub(rf"\b{re.escape(lang)}\b", "", text, flags=re.IGNORECASE)
    # Remove leftover separators (+, /, etc.) and extra spaces
    text = re.sub(r"\s*[+/|,]\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ------------------- Main Extractor -------------------

@dataclass
class ExtractedContent:
    """Dataclass holding extracted metadata from a Telegram caption/message."""

    title: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    quality: Optional[str] = None
    languages: Optional[List[str]] = None


def extract(content: str) -> ExtractedContent:
    """
    Extract title, year, season, episode, quality, and languages from a Telegram caption.

    Args:
        content: The raw caption string.

    Returns:
        ExtractedContent instance with available fields.
    """
    # Step 1: Clean the text (remove emojis, links, mentions, hashtags, sizes, codecs, format tags)
    cleaned = clean_text(content)

    # Step 2: Extract year and remove it
    year = extract_year(cleaned)
    if year is not None:
        cleaned = remove_year(cleaned, year)

    # Step 3: Extract season/episode and remove
    season, episode = extract_season_episode(cleaned)
    if season is not None:
        cleaned = remove_season_episode(cleaned, season, episode)

    # Step 4: Extract quality and remove
    quality = extract_quality(cleaned)
    if quality is not None:
        cleaned = remove_quality(cleaned, quality)

    # Step 5: Extract languages and remove
    languages = extract_languages(cleaned)
    if languages is not None:
        cleaned = remove_languages(cleaned, languages)

    # Step 6: The remaining text is the title
    title = cleaned.strip()
    if title == "":
        title = None

    return ExtractedContent(
        title=title,
        year=year,
        season=season,
        episode=episode,
        quality=quality,
        languages=languages,
    )


# ------------------- Example Usage (for testing) -------------------

if __name__ == "__main__":
    # Example caption
    caption = (
        "🔥 Pushpa 2 (2024)\n"
        "1080p WEB-DL\n"
        "Hindi + Telugu\n"
        "480p | 720p | 1080p\n"
        "Join @MoviesHub"
    )
    result = extract(caption)
    print(result)
    # Expected: title="Pushpa 2", year=2024, season=None, episode=None,
    # quality="1080p", languages=["hindi", "telugu"]