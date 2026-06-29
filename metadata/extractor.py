# extractor.py
"""
Compatibility layer for movie metadata extraction.
Delegates to the canonical parser in movie_parser.py.
"""

from typing import Optional, List

from coremovieshub.utils.movie_parser import parse_movie

from dataclasses import dataclass, field

@dataclass
class ExtractedContent:
    title: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    quality: Optional[str] = None
    languages: List[str] = field(default_factory=list)

    # NEW
    subtype: Optional[str] = None
    content_type: Optional[object] = None


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
        subtype=None,
    )