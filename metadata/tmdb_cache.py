# tmdb_cache.py
"""
Cache layer using TMDBMovie model with optional Telegram file ID deduplication.

This module provides:
    - normalize_title: consistent title normalization
    - find_by_title: retrieve cached content by normalized title
    - find_by_telegram_file_id: retrieve cached content by Telegram file ID
    - save_metadata: upsert metadata into TMDBMovie and, if telegram_file_id
                     is provided, link it to the movie via TelegramFile
                     (deduplication)
    - update_metadata: partial update of an existing record.

All operations are atomic and fully logged.
"""

import logging
import re
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist

# Import the real models from your project
from coremovieshub.models import TMDBMovie, TelegramFile as _TelegramFile

logger = logging.getLogger(__name__)


# ---------- Normalization ----------
def normalize_title(title: str) -> str:
    """
    Normalize a title for consistent lookup.

    - Lowercase
    - Remove punctuation (keep letters, digits, spaces)
    - Collapse spaces and strip

    Example: "Spider-Man: Across the Spider-Verse" -> "spider man across the spider verse"
    """
    if not title:
        return ""
    normalized = re.sub(r"[^\w\s]", " ", title.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


# ---------- Core functions ----------
def find_by_title(
    title: str,
    content_type: Optional[str] = None,
    year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached metadata by normalized title.

    Args:
        title: The title to search for.
        content_type: Optional filter (ignored for TMDBMovie, but kept for compatibility).
        year: Optional year filter (matches release_date__year if release_date is a DateField).

    Returns:
        Optional[Dict[str, Any]]: Metadata dict or None.
    """
    normalized = normalize_title(title)
    logger.debug(f"Searching TMDB cache for '{title}' (normalized='{normalized}')")

    queryset = TMDBMovie.objects.filter(title_normalized=normalized)

    if year is not None:
        queryset = queryset.filter(release_date__year=year)

    # content_type is not stored on TMDBMovie; we ignore it.
    movie = queryset.order_by("-vote_average").first()

    if not movie:
        logger.info(f"Cache miss: '{title}' not found in TMDB")
        return None

    logger.info(f"Cache hit: found '{movie.title}' (ID {movie.tmdb_id})")

    # Convert to a unified metadata dict (matches the common schema)
    return {
        "external_id": movie.tmdb_id,
        "source": "tmdb",
        "title": movie.title,
        "original_title": movie.original_title or "",
        "overview": movie.overview or "",
        "poster": movie.poster_path or "",
        "backdrop": movie.backdrop_path or "",
        "genres": movie.genres.split(",") if movie.genres else [],
        "release_date": movie.release_date.isoformat() if movie.release_date else None,
        "rating": movie.vote_average,
        "language": movie.original_language or "",
        "runtime": movie.runtime,
        "status": movie.status or "",
        "content_type": "movie",  # default; could be extended with a field
        "season_count": None,
        "episode_count": None,
    }


def find_by_telegram_file_id(telegram_file_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached metadata by Telegram file ID.

    Args:
        telegram_file_id: The unique Telegram file ID.

    Returns:
        Optional[Dict[str, Any]]: Metadata dict or None.
    """
    try:
        tg_file = _TelegramFile.objects.get(telegram_file_id=telegram_file_id)
        movie = tg_file.movie
        logger.info(f"Cache hit by telegram_file_id '{telegram_file_id}'")
        # Reuse the conversion logic
        return find_by_title(movie.title)
    except ObjectDoesNotExist:
        logger.info(f"Cache miss: telegram_file_id '{telegram_file_id}' not found")
        return None


@transaction.atomic
def save_metadata(
    data: Dict[str, Any],
    telegram_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Save (upsert) metadata into TMDBMovie and optionally link a Telegram file ID.

    If a movie with the same tmdb_id exists, it is updated.
    If telegram_file_id is provided, a TelegramFile entry is created/updated
    pointing to the movie.

    Args:
        data: Metadata dict (must contain "external_id" for tmdb_id).
        telegram_file_id: Optional unique Telegram file ID for deduplication.

    Returns:
        Dict[str, Any]: The saved metadata dict (converted from the movie).

    Raises:
        ValueError: If external_id is missing.
    """
    if "external_id" not in data:
        raise ValueError("Missing 'external_id' in metadata data")

    tmdb_id = data["external_id"]
    title = data.get("title", "")
    normalized = normalize_title(title)

    logger.info(f"Saving metadata for tmdb_id={tmdb_id}")

    # Build defaults with safe field filtering
    model_fields = {
        f.name
        for f in TMDBMovie._meta.get_fields()
        if hasattr(f, "attname")
    }

    defaults = {
        "title": title,
        "title_normalized": normalized,
        "poster_path": data.get("poster", ""),
        "backdrop_path": data.get("backdrop", ""),
        "overview": data.get("overview", ""),
        "genres": ",".join(data.get("genres", []))
            if isinstance(data.get("genres"), list)
            else data.get("genres", ""),
        "release_date": data.get("release_date"),
        "vote_average": data.get("rating", 0.0),
        "original_title": data.get("original_title", ""),
        "original_language": data.get("language", ""),
        "runtime": data.get("runtime"),
        "status": data.get("status", ""),
    }

    # Keep only fields that actually exist on the model
    defaults = {
        k: v
        for k, v in defaults.items()
        if k in model_fields
    }

    # Create or update the TMDBMovie
    movie, created = TMDBMovie.objects.update_or_create(
        tmdb_id=tmdb_id,
        defaults=defaults,
    )
    logger.debug(f"TMDBMovie {'created' if created else 'updated'} (ID {movie.id})")

    # If telegram_file_id is provided, link it to this movie
    if telegram_file_id:
        tg_file, tg_created = _TelegramFile.objects.update_or_create(
            telegram_file_id=telegram_file_id,
            defaults={"movie": movie},
        )
        logger.debug(f"TelegramFile {'created' if tg_created else 'updated'} for '{telegram_file_id}'")

    # Return the metadata dict (same as find_by_title would)
    return find_by_title(movie.title)  # reuse conversion


@transaction.atomic
def update_metadata(
    tmdb_id: str,
    data: Dict[str, Any],
    telegram_file_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update an existing TMDBMovie record by tmdb_id and optionally update its TelegramFile link.

    Args:
        tmdb_id: The TMDB ID.
        data: Partial metadata dict.
        telegram_file_id: Optional new Telegram file ID to associate.

    Returns:
        Optional[Dict[str, Any]]: Updated metadata dict or None if not found.
    """
    try:
        movie = TMDBMovie.objects.get(tmdb_id=tmdb_id)
    except ObjectDoesNotExist:
        logger.warning(f"Update failed: no movie with tmdb_id='{tmdb_id}'")
        return None

    # Apply updates (skip external_id, source)
    for key, value in data.items():
        if key not in ("external_id", "source"):
            if key == "genres" and isinstance(value, list):
                value = ",".join(value)
            # Map common keys to model fields if needed
            field_mapping = {
                "poster": "poster_path",
                "backdrop": "backdrop_path",
                "rating": "vote_average",
                "language": "original_language",
            }
            model_field = field_mapping.get(key, key)
            if hasattr(movie, model_field):
                setattr(movie, model_field, value)

    # Recompute normalized_title if title changed
    if "title" in data and data["title"]:
        movie.title_normalized = normalize_title(data["title"])

    movie.save()
    logger.info(f"Updated movie tmdb_id='{tmdb_id}'")

    # Update TelegramFile if provided
    if telegram_file_id:
        _TelegramFile.objects.update_or_create(
            telegram_file_id=telegram_file_id,
            defaults={"movie": movie},
        )

    return find_by_title(movie.title)


# ---------- Example usage (for testing) ----------
if __name__ == "__main__":
    # This module is meant to be used within a Django environment.
    # The following is a placeholder for manual testing.
    import django
    django.setup()  # if Django environment is available

    # Example: save some metadata
    test_data = {
        "external_id": "12345",
        "title": "Inception",
        "release_date": "2010-07-16",
        "rating": 8.8,
        "genres": ["Action", "Sci-Fi"],
        "overview": "A thief who steals corporate secrets...",
    }
    # save_metadata(test_data, telegram_file_id="abc123")
    # result = find_by_title("Inception")
    # print(result)
    pass