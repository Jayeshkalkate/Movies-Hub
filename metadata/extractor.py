# extractor.py
"""
Compatibility layer for movie metadata extraction.

This module provides a simple interface to the robust `movie_parser`
from `coremovieshub.utils`. It handles parsing of raw text (captions,
filenames) and returns structured metadata.

Public API:
    - ExtractedContent: dataclass holding title, year, season, episode,
                        quality, languages.
    - extract(text: str) -> ExtractedContent: main entry point.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# Import the actual parser
try:
    from coremovieshub.utils.movie_parser import parse_movie
except ImportError:
    # Fallback: define a dummy parser that returns empty data
    def parse_movie(text: str) -> Dict[str, Any]:
        return {}

# ---------- Logging ----------
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass
class ExtractedContent:
    """
    Structured metadata extracted from a text string.

    Attributes:
        title: The cleaned movie/show title.
        year: Release year (if found).
        season: Season number (if TV series).
        episode: Episode number (if TV series).
        quality: Video quality (e.g., "1080p").
        languages: List of detected language codes.
    """
    title: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    quality: Optional[str] = None
    languages: List[str] = field(default_factory=list)


# ---------- Public API ----------
def extract(text: str) -> ExtractedContent:
    """
    Parse movie metadata from raw text.

    This function wraps the `parse_movie` utility and converts its
    dictionary output into an `ExtractedContent` dataclass.

    Args:
        text: Raw caption or filename string.

    Returns:
        ExtractedContent: Structured metadata. If parsing fails,
                          an empty object with all None/empty fields is returned.
    """
    if not text:
        return ExtractedContent()

    try:
        data = parse_movie(text)
        # Ensure data is a dict (it should be)
        if not isinstance(data, dict):
            logger.warning(f"parse_movie returned non-dict: {data}")
            data = {}
    except Exception as e:
        logger.exception(f"Error parsing text: {text[:50]}... -> {e}")
        data = {}

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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    test_cases = [
        ("The.Matrix.1999.1080p.BluRay.x264-AAA", "Movie with year and quality"),
        ("Breaking.Bad.S01E02.1080p.WEB-DL", "TV episode"),
        ("Inception (2010) [1080p] [ENG,FRE]", "Movie with languages"),
        ("Stranger.Things.S02E03.4k.HDR", "TV with 4k"),
        ("Avatar (2009)", "Movie only"),
        ("Some.Show.Without.Year.S03E04", "TV without year"),
        ("RandomFile.mkv", "Fallback: just title"),
        ("File name:- Guardians of the Galaxy 2014 720p BluRay x264 AAC", "New test"),
        ("Audio: Hindi, English | Movie 2020 1080p", "Audio prefix test"),
    ]

    for text, desc in test_cases:
        result = extract(text)
        print(f"\n{desc}:")
        print(f"  Input: {text}")
        print(f"  Output: {result}")