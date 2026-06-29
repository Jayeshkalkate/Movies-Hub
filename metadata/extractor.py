# extractor.py
"""
Compatibility layer for movie metadata extraction.
Self-contained parser with full support for filenames and captions.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


# ---------- Logging ----------
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# ---------- Enums for content type ----------
class ContentType(Enum):
    MOVIE = "movie"
    TV = "tv"
    UNKNOWN = "unknown"


@dataclass
class ExtractedContent:
    title: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    quality: Optional[str] = None
    languages: List[str] = field(default_factory=list)

    # NEW fields
    subtype: Optional[str] = None          # e.g., "trailer", "clip", "feature"
    content_type: Optional[ContentType] = None


# ---------- Parser implementation ----------
class MovieParser:
    """
    Parses movie/TV metadata from a string using a chain of regex patterns.
    """

    # Patterns are ordered by specificity; first match wins.
    PATTERNS = [
        # TV: Show Name - S01E02 - Episode Title (year) [quality] {lang}
        re.compile(
            r'^(?P<title>.+?)\s*[-_]\s*S(?P<season>\d{1,2})E(?P<episode>\d{1,2})'
            r'(?:\s*[-_]\s*(?P<ep_title>.+?))?'
            r'(?:\s*[\(\[]\s*(?P<year>\d{4})\s*[\)\]])?'
            r'(?:\s*[\[\(]\s*(?P<quality>\d{3,4}p|[48]k|hdtv|web-dl|bluray)\s*[\]\)])?'
            r'(?:\s*[\[\(]\s*(?P<languages>[a-zA-Z]{2,3}(?:\s*[,/]\s*[a-zA-Z]{2,3})*)\s*[\]\)])?',
            re.IGNORECASE
        ),
        # TV: Show Name (year) S01E02 ...
        re.compile(
            r'^(?P<title>.+?)\s*[\(\[]\s*(?P<year>\d{4})\s*[\)\]]'
            r'\s*S(?P<season>\d{1,2})E(?P<episode>\d{1,2})'
            r'(?:\s*[-_]\s*(?P<ep_title>.+?))?'
            r'(?:\s*[\[\(]\s*(?P<quality>\d{3,4}p|[48]k|hdtv|web-dl|bluray)\s*[\]\)])?'
            r'(?:\s*[\[\(]\s*(?P<languages>[a-zA-Z]{2,3}(?:\s*[,/]\s*[a-zA-Z]{2,3})*)\s*[\]\)])?',
            re.IGNORECASE
        ),
        # Movie: Title (year) [quality] {lang}
        re.compile(
            r'^(?P<title>.+?)\s*[\(\[]\s*(?P<year>\d{4})\s*[\)\]]'
            r'(?:\s*[\[\(]\s*(?P<quality>\d{3,4}p|[48]k|hdtv|web-dl|bluray)\s*[\]\)])?'
            r'(?:\s*[\[\(]\s*(?P<languages>[a-zA-Z]{2,3}(?:\s*[,/]\s*[a-zA-Z]{2,3})*)\s*[\]\)])?',
            re.IGNORECASE
        ),
        # Movie: Title (year) - simple
        re.compile(
            r'^(?P<title>.+?)\s*[\(\[]\s*(?P<year>\d{4})\s*[\)\]]',
            re.IGNORECASE
        ),
        # Fallback: just title (no year, no extra)
        re.compile(
            r'^(?P<title>.+?)'
            r'(?:\s*[\[\(]\s*(?P<quality>\d{3,4}p|[48]k|hdtv|web-dl|bluray)\s*[\]\)])?'
            r'(?:\s*[\[\(]\s*(?P<languages>[a-zA-Z]{2,3}(?:\s*[,/]\s*[a-zA-Z]{2,3})*)\s*[\]\)])?$',
            re.IGNORECASE
        ),
    ]

    @classmethod
    def parse(cls, text: str) -> Dict[str, Any]:
        """
        Parse the input string and return a dictionary of metadata.
        """
        text = text.strip()
        if not text:
            return {}

        for pattern in cls.PATTERNS:
            match = pattern.match(text)
            if match:
                data = match.groupdict()
                # Clean up and convert types
                result = {}
                if data.get('title'):
                    # Remove common noise like file extensions and dots
                    title = data['title'].strip()
                    title = re.sub(r'\.[a-zA-Z0-9]{2,4}$', '', title)  # remove extension
                    title = re.sub(r'[._]', ' ', title)                # replace dots/underscores
                    title = re.sub(r'\s+', ' ', title).strip()
                    result['title'] = title

                if data.get('year'):
                    try:
                        result['year'] = int(data['year'])
                    except ValueError:
                        pass

                if data.get('season'):
                    try:
                        result['season'] = int(data['season'])
                    except ValueError:
                        pass

                if data.get('episode'):
                    try:
                        result['episode'] = int(data['episode'])
                    except ValueError:
                        pass

                if data.get('quality'):
                    result['quality'] = data['quality'].strip().lower()

                if data.get('languages'):
                    # Split by comma or slash, strip whitespace
                    raw = data['languages']
                    langs = re.split(r'[,/]\s*', raw)
                    result['languages'] = [lang.strip().upper() for lang in langs if lang.strip()]

                # Determine content type
                if result.get('season') is not None and result.get('episode') is not None:
                    result['content_type'] = ContentType.TV
                else:
                    result['content_type'] = ContentType.MOVIE

                # Subtype (not implemented yet, could be inferred from filename)
                result['subtype'] = None

                logger.debug(f"Parsed: {result}")
                return result

        # If nothing matched, return empty (will be handled by caller)
        logger.warning(f"No pattern matched for text: {text[:100]}")
        return {}

# ---------- Public API ----------
def extract(text: str) -> ExtractedContent:
    """
    Parse movie metadata from text.

    Args:
        text: Raw caption or filename string.

    Returns:
        ExtractedContent object with title, year, season, etc.
    """
    data = MovieParser.parse(text)
    return ExtractedContent(
        title=data.get("title"),
        year=data.get("year"),
        season=data.get("season"),
        episode=data.get("episode"),
        quality=data.get("quality"),
        languages=data.get("languages") or [],
        subtype=data.get("subtype"),
        content_type=data.get("content_type"),
    )


# ---------- Simple self-test (run with python extractor.py) ----------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    test_cases = [
        ("The.Matrix.1999.1080p.BluRay.x264-AAA", "Movie with year and quality"),
        ("Breaking.Bad.S01E02.1080p.WEB-DL", "TV episode"),
        ("Inception (2010) [1080p] [ENG,FRE]", "Movie with languages"),
        ("Stranger.Things.S02E03.4k.HDR", "TV with 4k"),
        ("Avatar (2009)", "Movie only"),
        ("Some.Show.Without.Year.S03E04", "TV without year"),
        ("RandomFile.mkv", "Fallback: just title"),
    ]

    for text, desc in test_cases:
        result = extract(text)
        print(f"\n{desc}:")
        print(f"  Input: {text}")
        print(f"  Output: {result}")
        print(f"  content_type: {result.content_type}")
        
