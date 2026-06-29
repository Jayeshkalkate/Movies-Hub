"""
Metadata formatter for various providers.

This module provides functions to convert raw API responses from different
content providers (TMDb, TVMaze, Jikan, AniList) into a common metadata schema.

The schema is a dictionary with the following keys:
    - external_id: str, provider-specific identifier
    - source: str, provider name (e.g., "tmdb", "tvmaze", "jikan", "anilist")
    - title: str, main title
    - original_title: str, original title (fallback to main title)
    - overview: str, synopsis/description (empty string if missing)
    - poster: str, URL to poster image (empty if missing)
    - backdrop: str, URL to backdrop/background image (empty if missing)
    - genres: List[str], list of genre names
    - release_date: str, date in YYYY-MM-DD format (or year as string)
    - rating: float, average rating normalized to 0-10 scale
    - language: str, original language code (or empty)
    - runtime: int or None, duration in minutes
    - status: str, release/airing status (e.g., "Released", "Airing", "Ended")
    - content_type: str, "movie" or "tv"
    - season_count: int or None, number of seasons (for TV)
    - episode_count: int or None, number of episodes (for TV)

All functions are pure (no API calls) and safe against missing fields.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Union, Callable

logger = logging.getLogger(__name__)


# ------------------- Helper Functions -------------------

def _safe_get(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    Safely navigate nested dictionaries with fallback.

    Args:
        data: Dictionary to traverse.
        *keys: Sequence of keys to access.
        default: Default value if any key is missing or value is None.

    Returns:
        The value at the nested path, or default if not found.
    """
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return default
        else:
            return default
    return current if current is not None else default


def _build_genre_list(genres_data: Any) -> List[str]:
    """
    Extract genre names from various provider formats.

    Args:
        genres_data: A list of strings or list of dicts with 'name' key.

    Returns:
        List[str]: List of genre names.
    """
    if not genres_data:
        return []
    if isinstance(genres_data, list):
        if all(isinstance(g, str) for g in genres_data):
            return [g for g in genres_data if g]
        if all(isinstance(g, dict) for g in genres_data):
            return [g.get('name', '') for g in genres_data if g.get('name')]
    # If it's a single dict with names? Unlikely.
    return []


def _build_date(year: Optional[int], month: Optional[int], day: Optional[int]) -> str:
    """
    Build YYYY-MM-DD from components, falling back to year-only string.

    Args:
        year: Year integer.
        month: Month integer (1-12).
        day: Day integer (1-31).

    Returns:
        str: Formatted date or year string, or empty if nothing provided.
    """
    if year is not None and month is not None and day is not None:
        try:
            return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, TypeError):
            pass
    if year is not None:
        return str(year)
    return ""


def _normalize_rating(rating: Optional[Union[int, float]], scale: int = 10) -> float:
    """
    Normalize rating to 0-10 scale.

    Args:
        rating: Raw rating value.
        scale: The scale the rating is on (e.g., 10, 100).

    Returns:
        float: Rating normalized to 0-10, or 0.0 if invalid.
    """
    if rating is None:
        return 0.0
    try:
        val = float(rating)
        if scale <= 0:
            return 0.0
        return round(val / scale * 10, 1)
    except (ValueError, TypeError):
        return 0.0


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string using regex."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


# ------------------- Provider Formatters -------------------

def format_tmdb(item: Dict[str, Any], content_type: str = "movie") -> Dict[str, Any]:
    """
    Format a TMDb API response item into the common schema.

    Args:
        item: The raw JSON object from TMDb (movie or TV show).
        content_type: Either "movie" or "tv" to guide field selection.

    Returns:
        Dict[str, Any]: Common metadata schema.
    """
    is_movie = content_type == "movie"
    source = "tmdb"

    # Common fields with safe extraction
    external_id = str(item.get("id", ""))
    title = item.get("title") if is_movie else item.get("name", "")
    original_title = item.get("original_title") if is_movie else item.get("original_name", "")
    overview = item.get("overview", "")
    release_date = item.get("release_date") if is_movie else item.get("first_air_date", "")
    rating = _normalize_rating(item.get("vote_average"), scale=10)
    language = item.get("original_language", "")
    status = item.get("status", "")

    # Images: construct full URLs
    poster_path = item.get("poster_path")
    backdrop_path = item.get("backdrop_path")
    base_url = "https://image.tmdb.org/t/p/original"
    poster = f"{base_url}{poster_path}" if poster_path else ""
    backdrop = f"{base_url}{backdrop_path}" if backdrop_path else ""

    # Genres
    genres_data = item.get("genres", [])
    genres = _build_genre_list(genres_data)

    # Runtime / episode info
    if is_movie:
        runtime = item.get("runtime")
        episode_count = None
        season_count = None
    else:
        runtime = None  # TV shows have per-episode runtime, not overall
        season_count = item.get("number_of_seasons")
        episode_count = item.get("number_of_episodes")

    content_type_out = "movie" if is_movie else "tv"

    return {
        "external_id": external_id,
        "source": source,
        "title": title or "",
        "original_title": original_title or title or "",
        "overview": overview or "",
        "poster": poster,
        "backdrop": backdrop,
        "genres": genres,
        "release_date": release_date or "",
        "rating": rating,
        "language": language,
        "runtime": runtime,
        "status": status,
        "content_type": content_type_out,
        "season_count": season_count,
        "episode_count": episode_count,
    }


def format_tvmaze(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a TVMaze API response item into the common schema.

    Supports both the 'show' object from search and direct show response.

    Args:
        item: The raw JSON object from TVMaze (a show).

    Returns:
        Dict[str, Any]: Common metadata schema.
    """
    source = "tvmaze"

    # If the item is from search, it has a 'show' key
    if "show" in item:
        item = item["show"]

    external_id = str(item.get("id", ""))
    title = item.get("name", "")
    original_title = title  # TVMaze doesn't have an original title field
    overview = _strip_html(item.get("summary", ""))

    premiered = item.get("premiered", "")
    release_date = premiered if premiered else ""

    rating_data = item.get("rating", {})
    rating = _normalize_rating(rating_data.get("average"), scale=10)

    language = item.get("language", "")
    status = item.get("status", "")

    image_data = item.get("image", {})
    poster = image_data.get("original", "") or image_data.get("medium", "")
    backdrop = ""  # TVMaze does not have a backdrop

    genres = item.get("genres", [])

    runtime = item.get("runtime")

    # Seasons / episodes: if embedded, we can get count
    embedded = item.get("_embedded", {})
    seasons = embedded.get("seasons", [])
    if seasons and isinstance(seasons, list):
        season_count = len(seasons)
        episode_count = sum(s.get("episodeOrder", 0) for s in seasons if isinstance(s, dict) and s.get("episodeOrder"))
    else:
        season_count = None
        episode_count = None

    content_type_out = "tv"

    return {
        "external_id": external_id,
        "source": source,
        "title": title,
        "original_title": original_title,
        "overview": overview,
        "poster": poster,
        "backdrop": backdrop,
        "genres": genres,
        "release_date": release_date,
        "rating": rating,
        "language": language,
        "runtime": runtime,
        "status": status,
        "content_type": content_type_out,
        "season_count": season_count,
        "episode_count": episode_count,
    }


def format_jikan(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a Jikan API response item into the common schema.

    Args:
        item: The raw JSON object from Jikan (anime entry).

    Returns:
        Dict[str, Any]: Common metadata schema.
    """
    source = "jikan"

    external_id = str(item.get("mal_id", ""))
    title = item.get("title", "")
    original_title = item.get("title_japanese", "") or item.get("title_english", "") or title

    synopsis = item.get("synopsis", "")
    overview = synopsis or ""

    images = item.get("images", {})
    jpg = images.get("jpg", {})
    poster = jpg.get("large_image_url", "") or jpg.get("image_url", "")
    backdrop = ""  # Jikan doesn't provide a backdrop

    genres_data = item.get("genres", [])
    genres = _build_genre_list(genres_data)

    aired = item.get("aired", {})
    from_date = aired.get("from")
    if from_date:
        release_date = from_date.split("T")[0]  # YYYY-MM-DD
    else:
        release_date = ""

    score = item.get("score")
    rating = _normalize_rating(score, scale=10)

    language = ""  # Jikan doesn't provide language

    duration_str = item.get("duration", "")
    runtime = None
    if duration_str:
        match = re.search(r"(\d+)", duration_str)
        if match:
            runtime = int(match.group(1))

    status = item.get("status", "")

    anime_type = item.get("type", "")
    if anime_type.lower() in ("tv", "tv series", "tv special"):
        content_type_out = "tv"
    elif anime_type.lower() in ("movie", "film"):
        content_type_out = "movie"
    else:
        episodes = item.get("episodes")
        if episodes is not None and episodes > 1:
            content_type_out = "tv"
        else:
            content_type_out = "movie"

    if content_type_out == "tv":
        episode_count = item.get("episodes")
        season_count = None
    else:
        season_count = None
        episode_count = None

    return {
        "external_id": external_id,
        "source": source,
        "title": title,
        "original_title": original_title,
        "overview": overview,
        "poster": poster,
        "backdrop": backdrop,
        "genres": genres,
        "release_date": release_date,
        "rating": rating,
        "language": language,
        "runtime": runtime,
        "status": status,
        "content_type": content_type_out,
        "season_count": season_count,
        "episode_count": episode_count,
    }


def format_anilist(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format an AniList GraphQL response item into the common schema.

    Args:
        item: The raw JSON object from AniList (Media object).

    Returns:
        Dict[str, Any]: Common metadata schema.
    """
    source = "anilist"

    external_id = str(item.get("id", ""))
    title_data = item.get("title", {})
    title = title_data.get("romaji", "") or title_data.get("english", "")
    original_title = title_data.get("native", "") or title_data.get("english", "") or title

    description = item.get("description", "")
    overview = _strip_html(description) if description else ""

    cover = item.get("coverImage", {})
    poster = cover.get("large", "") or cover.get("medium", "")
    backdrop = item.get("bannerImage", "")

    genres = item.get("genres", [])

    start = item.get("startDate", {})
    release_date = _build_date(start.get("year"), start.get("month"), start.get("day"))

    score = item.get("averageScore")
    rating = _normalize_rating(score, scale=100)

    language = item.get("countryOfOrigin", "")

    runtime = item.get("duration")

    status_raw = item.get("status", "")
    status_map = {
        "FINISHED": "Ended",
        "RELEASING": "Airing",
        "NOT_YET_RELEASED": "Not Yet Aired",
        "CANCELLED": "Cancelled",
        "HIATUS": "Hiatus",
    }
    status = status_map.get(status_raw, status_raw)

    format_type = item.get("format", "")
    if format_type in ("TV", "TV_SHORT", "TV_SPECIAL", "OVA", "ONA", "SPECIAL"):
        content_type_out = "tv"
    elif format_type in ("MOVIE", "FILM"):
        content_type_out = "movie"
    else:
        episodes = item.get("episodes")
        if episodes is not None and episodes > 1:
            content_type_out = "tv"
        else:
            content_type_out = "movie"

    if content_type_out == "tv":
        episode_count = item.get("episodes")
        season_count = None
    else:
        season_count = None
        episode_count = None

    return {
        "external_id": external_id,
        "source": source,
        "title": title,
        "original_title": original_title,
        "overview": overview,
        "poster": poster,
        "backdrop": backdrop,
        "genres": genres,
        "release_date": release_date,
        "rating": rating,
        "language": language,
        "runtime": runtime,
        "status": status,
        "content_type": content_type_out,
        "season_count": season_count,
        "episode_count": episode_count,
    }


# ------------------- Provider Registry and Auto-Dispatch -------------------

PROVIDER_FORMATTERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "tmdb": lambda data: format_tmdb(data, data.get("media_type", "movie")),
    "tvmaze": format_tvmaze,
    "jikan": format_jikan,
    "anilist": format_anilist,
}


def format_metadata(source: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Automatically select and apply the appropriate formatter based on source.

    Args:
        source: Provider name (e.g., 'tmdb', 'tvmaze', 'jikan', 'anilist').
        data: Raw API response data.

    Returns:
        Dict[str, Any]: Common metadata schema.

    Raises:
        ValueError: If the source is not supported.
    """
    source_lower = source.lower()
    formatter = PROVIDER_FORMATTERS.get(source_lower)
    if not formatter:
        raise ValueError(f"Unsupported source: {source}. Supported: {list(PROVIDER_FORMATTERS.keys())}")
    return formatter(data)


# ------------------- Example Usage and Testing -------------------

if __name__ == "__main__":
    import json

    # Sample TMDb movie response
    sample_tmdb_movie = {
        "id": 27205,
        "title": "Inception",
        "original_title": "Inception",
        "overview": "A thief who steals corporate secrets...",
        "release_date": "2010-07-16",
        "vote_average": 8.4,
        "poster_path": "/9gk7adHYeDvHkCSEqAvQNLV5Uge.jpg",
        "backdrop_path": "/s3TBrRGB1iav7HPzwXDRQ4j7kH.jpg",
        "genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}],
        "original_language": "en",
        "runtime": 148,
        "status": "Released"
    }
    formatted = format_tmdb(sample_tmdb_movie, "movie")
    print("TMDb Movie:")
    print(json.dumps(formatted, indent=2))

    # Sample TVMaze show
    sample_tvmaze = {
        "id": 1,
        "name": "Under the Dome",
        "summary": "<p><b>Under the Dome</b> is the story of a small town...",
        "premiered": "2013-06-24",
        "rating": {"average": 6.9},
        "language": "English",
        "status": "Ended",
        "image": {"original": "https://static.tvmaze.com/images/original/1/1.jpg"},
        "genres": ["Drama", "Science-Fiction", "Thriller"],
        "runtime": 60,
        "_embedded": {
            "seasons": [
                {"episodeOrder": 13},
                {"episodeOrder": 13},
                {"episodeOrder": 13}
            ]
        }
    }
    formatted = format_tvmaze(sample_tvmaze)
    print("\nTVMaze Show:")
    print(json.dumps(formatted, indent=2))

    # Sample Jikan anime
    sample_jikan = {
        "mal_id": 20,
        "title": "Naruto",
        "title_japanese": "NARUTO -ナルト-",
        "title_english": "Naruto",
        "synopsis": "Naruto Uzumaki is a young ninja...",
        "images": {"jpg": {"large_image_url": "https://cdn.myanimelist.net/images/anime/13/17405.jpg"}},
        "genres": [{"name": "Action"}, {"name": "Adventure"}],
        "aired": {"from": "2002-10-03T00:00:00+00:00"},
        "score": 8.15,
        "duration": "24 min per ep",
        "status": "Finished Airing",
        "type": "TV",
        "episodes": 220
    }
    formatted = format_jikan(sample_jikan)
    print("\nJikan Anime:")
    print(json.dumps(formatted, indent=2))

    # Sample AniList media
    sample_anilist = {
        "id": 100,
        "title": {"romaji": "Naruto", "english": "Naruto", "native": "NARUTO -ナルト-"},
        "description": "Naruto Uzumaki is a young ninja...",
        "coverImage": {"large": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx100.jpg"},
        "bannerImage": "https://s4.anilist.co/file/anilistcdn/media/anime/banner/100.jpg",
        "genres": ["Action", "Adventure"],
        "startDate": {"year": 2002, "month": 10, "day": 3},
        "averageScore": 79,
        "countryOfOrigin": "JP",
        "duration": 24,
        "status": "FINISHED",
        "format": "TV",
        "episodes": 220
    }
    formatted = format_anilist(sample_anilist)
    print("\nAniList Media:")
    print(json.dumps(formatted, indent=2))

    # Test auto-dispatch
    print("\nAuto-dispatch test:")
    auto = format_metadata("tmdb", sample_tmdb_movie | {"media_type": "movie"})
    print(json.dumps(auto, indent=2))
    
