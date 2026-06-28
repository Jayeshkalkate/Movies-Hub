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
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ------------------- Helper Functions -------------------

def _safe_get(data: Dict[str, Any], *keys, default=None) -> Any:
    """Safely navigate nested dictionaries with fallback."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data if data is not None else default


def _build_genre_list(genres_data: Any) -> List[str]:
    """Extract genre names from various provider formats."""
    if not genres_data:
        return []
    # If it's a list of strings
    if isinstance(genres_data, list):
        if all(isinstance(g, str) for g in genres_data):
            return genres_data
        # If it's a list of objects with 'name' key
        if all(isinstance(g, dict) for g in genres_data):
            return [g.get('name', '') for g in genres_data if g.get('name')]
    # If it's a dict with 'nodes' or similar? Not needed for providers we handle.
    return []


def _build_date(year: Optional[int], month: Optional[int], day: Optional[int]) -> str:
    """Build YYYY-MM-DD from components, falling back to year."""
    if year and month and day:
        try:
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            pass
    if year:
        return str(year)
    return ""


def _normalize_rating(rating: Optional[float], scale: int = 10) -> float:
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
        return round(val / scale * 10, 1)
    except (ValueError, TypeError):
        return 0.0


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

    # Common fields
    external_id = str(item.get("id", ""))
    title = item.get("title") if is_movie else item.get("name", "")
    original_title = item.get("original_title") if is_movie else item.get("original_name", "")
    overview = item.get("overview", "")
    release_date = item.get("release_date") if is_movie else item.get("first_air_date", "")
    rating = _normalize_rating(item.get("vote_average", 0.0), scale=10)
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
        runtime = None  # TV shows have episode durations, but we don't have per-episode
        season_count = item.get("number_of_seasons")
        episode_count = item.get("number_of_episodes")

    # Content type
    content_type_out = "movie" if is_movie else "tv"

    return {
        "external_id": external_id,
        "source": source,
        "title": title,
        "original_title": original_title or title,
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
    original_title = item.get("name", "")  # TVMaze doesn't have original title
    overview = item.get("summary", "").strip()
    # Remove HTML tags from summary (simple)
    import re
    overview = re.sub(r"<[^>]+>", "", overview)

    # Release date
    premiered = item.get("premiered", "")
    release_date = premiered if premiered else ""

    # Rating (average, already 0-10)
    rating_data = item.get("rating", {})
    rating = _normalize_rating(rating_data.get("average"), scale=10)

    language = item.get("language", "")
    status = item.get("status", "")

    # Images
    image_data = item.get("image", {})
    poster = image_data.get("original", "") or image_data.get("medium", "")
    backdrop = ""  # TVMaze does not have a backdrop/background image

    # Genres
    genres = item.get("genres", [])

    # Runtime
    runtime = item.get("runtime")

    # Seasons / episodes: if embedded, we can get count
    embedded = item.get("_embedded", {})
    seasons = embedded.get("seasons", [])
    if seasons and isinstance(seasons, list):
        season_count = len(seasons)
        # Estimate episode count by summing episodes per season if available
        episode_count = sum(s.get("episodeOrder", 0) for s in seasons if s.get("episodeOrder"))
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
    overview = synopsis

    # Images
    images = item.get("images", {})
    jpg = images.get("jpg", {})
    poster = jpg.get("large_image_url", "") or jpg.get("image_url", "")
    backdrop = ""  # Jikan doesn't provide a backdrop, only poster

    # Genres
    genres_data = item.get("genres", [])
    genres = _build_genre_list(genres_data)

    # Release date: use aired.from
    aired = item.get("aired", {})
    from_date = aired.get("from")
    if from_date:
        release_date = from_date.split("T")[0]  # YYYY-MM-DD
    else:
        release_date = ""

    # Rating
    score = item.get("score")
    rating = _normalize_rating(score, scale=10)

    # Language - Jikan doesn't provide language; we can leave empty
    language = ""

    # Runtime: duration string like "24 min per ep" - we can parse first number
    duration_str = item.get("duration", "")
    runtime = None
    if duration_str:
        import re
        match = re.search(r"(\d+)", duration_str)
        if match:
            runtime = int(match.group(1))

    # Status: Jikan uses "Airing", "Finished", "Not yet aired"
    status = item.get("status", "")

    # Content type: from 'type' field: "TV", "Movie", "OVA", etc.
    anime_type = item.get("type", "")
    if anime_type.lower() in ("tv", "tv series", "tv special"):
        content_type_out = "tv"
    elif anime_type.lower() in ("movie", "film"):
        content_type_out = "movie"
    else:
        # Fallback: if episodes > 1, treat as tv
        episodes = item.get("episodes")
        if episodes is not None and episodes > 1:
            content_type_out = "tv"
        else:
            content_type_out = "movie"

    # Season/episode counts
    if content_type_out == "tv":
        episode_count = item.get("episodes")
        # Jikan doesn't provide season count; we can leave null
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
    original_title = title_data.get("native", "") or title_data.get("english", "")

    description = item.get("description", "")
    overview = description

    # Images
    cover = item.get("coverImage", {})
    poster = cover.get("large", "") or cover.get("medium", "")
    backdrop = item.get("bannerImage", "")

    # Genres
    genres = item.get("genres", [])

    # Release date: from startDate
    start = item.get("startDate", {})
    release_date = _build_date(start.get("year"), start.get("month"), start.get("day"))

    # Rating: averageScore is out of 100
    score = item.get("averageScore")
    rating = _normalize_rating(score, scale=100)

    # Language: countryOfOrigin (ISO code) - e.g., "JP"
    language = item.get("countryOfOrigin", "")

    # Runtime: duration in minutes per episode (for TV) or movie runtime?
    runtime = item.get("duration")

    # Status: AniList uses "FINISHED", "RELEASING", "NOT_YET_RELEASED", etc.
    status_raw = item.get("status", "")
    # Map to common status strings
    status_map = {
        "FINISHED": "Ended",
        "RELEASING": "Airing",
        "NOT_YET_RELEASED": "Not Yet Aired",
        "CANCELLED": "Cancelled",
        "HIATUS": "Hiatus",
    }
    status = status_map.get(status_raw, status_raw)

    # Content type: from format field (TV, MOVIE, OVA, etc.)
    format_type = item.get("format", "")
    if format_type in ("TV", "TV_SHORT", "TV_SPECIAL", "OVA", "ONA", "SPECIAL"):
        content_type_out = "tv"
    elif format_type in ("MOVIE", "FILM"):
        content_type_out = "movie"
    else:
        # Fallback: if episodes > 1 -> tv, else movie
        episodes = item.get("episodes")
        if episodes is not None and episodes > 1:
            content_type_out = "tv"
        else:
            content_type_out = "movie"

    # Episode and season counts
    if content_type_out == "tv":
        episode_count = item.get("episodes")
        # AniList doesn't directly provide season count; we can try to infer from relations? Not reliable.
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


# ------------------- Testing / Example Usage -------------------

if __name__ == "__main__":
    import json

    # Sample TMDb movie response (simplified)
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