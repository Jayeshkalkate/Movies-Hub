"""
Content type detector for movies, TV shows, and anime.

Enhanced with:
- Subtype detection (OVA, ONA, Movie, Special, Final Season, Part 2)
- Fallback season/episode parsing from title (E120, S02E08, etc.)
- Language detection from text
"""

import logging
import json
import os
import re
from enum import Enum
from typing import Optional, Set, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ContentType(Enum):
    MOVIE = "movie"
    TV = "tv"
    ANIME = "anime"
    UNKNOWN = "unknown"


# ---------- ExtractedContent (if not imported) ----------
try:
    from extractor import ExtractedContent
except ImportError:
    @dataclass
    class ExtractedContent:
        title: Optional[str] = None
        year: Optional[int] = None
        season: Optional[int] = None
        episode: Optional[int] = None
        quality: Optional[str] = None
        languages: Optional[List[str]] = None
        subtype: Optional[str] = None          # NEW: OVA, ONA, etc.


# ---------- Anime data (unchanged) ----------
BASE_ANIME_TITLES = { ... }   # (same as original, keep full set)

ANIME_KEYWORDS = { ... }      # (same as original)

def _load_anime_list() -> Set[str]:
    ... # (same as original)

ANIME_TITLES = _load_anime_list()


# ---------- NEW: Episode pattern parsing ----------
EPISODE_PATTERNS = [
    # S02E08, S2E8
    re.compile(r'(?i)[Ss](\d{1,2})[Ee](\d{1,3})'),
    # Season 2 Episode 8, season 02 episode 08
    re.compile(r'(?i)season\s*(\d{1,2})\s*(?:episode|ep)\s*(\d{1,3})'),
    # E120, Ep120, Episode-12
    re.compile(r'(?i)(?:[Ee]p(?:isode)?)[\s\-]?(\d{1,4})'),
    # Just a number like "Episode 12" (already covered above)
]

def parse_episode_info(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Scan text for season/episode patterns.
    Returns (season, episode) or (None, None).
    """
    if not text:
        return None, None
    for pat in EPISODE_PATTERNS:
        match = pat.search(text)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                # S02E08 -> season=2, episode=8
                try:
                    season = int(groups[0])
                    episode = int(groups[1])
                    return season, episode
                except ValueError:
                    continue
            elif len(groups) == 1:
                # E120 -> only episode number
                try:
                    episode = int(groups[0])
                    return None, episode
                except ValueError:
                    continue
    return None, None


# ---------- NEW: Language detection ----------
LANGUAGE_KEYWORDS = {
    'hindi': 'hi',
    'tamil': 'ta',
    'telugu': 'te',
    'english': 'en',
    'japanese': 'ja',
    'korean': 'ko',
    'dual audio': 'dual',
    'multi audio': 'multi',
    'multi-audio': 'multi',
    'dubbed': 'dub',
    'subbed': 'sub',
}

def detect_languages(text: str) -> List[str]:
    """
    Return a list of ISO language codes (or special tokens like 'dual', 'multi')
    found in the given text.
    """
    if not text:
        return []
    text_lower = text.lower()
    found = set()
    for keyword, code in LANGUAGE_KEYWORDS.items():
        if keyword in text_lower:
            found.add(code)
    # Also check for common patterns like "Hindi + Tamil + Telugu"
    # simple split by '+' or '&'
    for sep in ['+', '&', ',']:
        parts = text_lower.split(sep)
        if len(parts) > 1:
            for part in parts:
                part = part.strip()
                for keyword, code in LANGUAGE_KEYWORDS.items():
                    if keyword in part:
                        found.add(code)
    return list(found)


# ---------- Subtype detection (for anime) ----------
ANIME_SUBTYPE_KEYWORDS = {
    'ova': 'OVA',
    'ona': 'ONA',
    'movie': 'Movie',
    'special': 'Special',
    'final season': 'Final Season',
    'part 2': 'Part 2',
    'part ii': 'Part 2',
    'part 3': 'Part 3',
    'part iii': 'Part 3',
}

def detect_anime_subtype(title: str) -> Optional[str]:
    """Return subtype string if found, else None."""
    if not title:
        return None
    title_lower = title.lower()
    for key, subtype in ANIME_SUBTYPE_KEYWORDS.items():
        if key in title_lower:
            return subtype
    return None


# ---------- Main detection function ----------
def detect(extracted: ExtractedContent) -> ContentType:
    """
    Determine content type and also populate extracted.subtype and extracted.languages.
    """
    if extracted.title is None:
        logger.debug("Title is None, cannot classify.")
        return ContentType.UNKNOWN

    title = extracted.title.strip()
    title_lower = title.lower()
    logger.debug(f"Classifying title: '{title}'")

    # ----- 1. Try to parse season/episode if not already present -----
    if extracted.season is None and extracted.episode is None:
        season, episode = parse_episode_info(title)
        if season is not None or episode is not None:
            extracted.season = season
            extracted.episode = episode
            logger.debug(f"Parsed season={season}, episode={episode} from title")

    # ----- 2. Detect languages from title (or from other fields if available) -----
    # We can combine title with other text? We only have title here.
    # Manager can call a separate language detection on the full caption.
    # We'll set languages if not already present.
    if not extracted.languages:
        langs = detect_languages(title)
        if langs:
            extracted.languages = langs
            logger.debug(f"Detected languages from title: {langs}")

    # ----- 3. TV detection via season/episode -----
    if extracted.season is not None or extracted.episode is not None:
        logger.info(f"Detected TV show (season/episode present): '{title}'")
        # Check if anime and subtype
        if title_lower in ANIME_TITLES or any(kw in title_lower for kw in ANIME_KEYWORDS):
            # It's anime with episodes → could be TV series, OVA, ONA, etc.
            subtype = detect_anime_subtype(title)
            extracted.subtype = subtype
            if subtype in ('OVA', 'ONA', 'Special', 'Movie'):
                # Still ANIME, but we keep the type as ANIME (or maybe we could map to TV?)
                # We'll keep as ANIME because it's anime content.
                logger.info(f"Anime subtype: {subtype}")
                return ContentType.ANIME
            else:
                return ContentType.TV
        else:
            return ContentType.TV

    # ----- 4. Anime detection -----
    if title_lower in ANIME_TITLES:
        extracted.subtype = detect_anime_subtype(title)
        logger.info(f"Detected anime (exact match): '{title}', subtype={extracted.subtype}")
        return ContentType.ANIME

    for keyword in ANIME_KEYWORDS:
        if keyword in title_lower:
            extracted.subtype = detect_anime_subtype(title)
            logger.info(f"Detected anime (keyword '{keyword}'): '{title}', subtype={extracted.subtype}")
            return ContentType.ANIME

    # ----- 5. Fallback to movie -----
    logger.info(f"Detected movie (fallback): '{title}'")
    return ContentType.MOVIE


# Example test (keep as before, update test cases)
if __name__ == "__main__":
    ...  # (update test cases with new fields)
    
