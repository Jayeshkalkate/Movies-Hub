# extractor.py
"""
Compatibility layer for movie metadata extraction.
Self-contained parser with full support for filenames and captions.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
from coremovieshub.utils.movie_parser import parse_movie

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



# ---------- Public API ----------
def extract(text: str) -> ExtractedContent:
    """
    Parse movie metadata from text.

    Args:
        text: Raw caption or filename string.

    Returns:
        ExtractedContent object with title, year, season, etc.
    """
    data = parse_movie(text)
    return ExtractedContent(
        title=data.get("title"),
        year=data.get("year"),
        season=data.get("season"),
        episode=data.get("episode"),
        quality=data.get("quality"),
        languages=data.get("languages") or [],
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
        
