"""
Unified cache layer for metadata using Django ORM with TMDBMovie model.

This module provides functions to interact with the database for caching
metadata from external providers. It does NOT call any external APIs.

It provides:
    - find_by_title: retrieve cached content by title (with optional year)
    - find_by_external_id: retrieve cached content by provider ID and source
    - find_by_telegram_file_id: placeholder (not implemented)
    - save_metadata: upsert (create or update) metadata from a dict
    - update_metadata: update an existing record by external_id and source
    - delete_metadata: delete a cached entry by external_id and source

All operations use database transactions and include comprehensive logging.
"""

import logging
import re
import os
from typing import Optional, Dict, Any

from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from coremovieshub.models import TMDBMovie

logger = logging.getLogger(__name__)

# ---------- Configuration ----------
CACHE_EXPIRY_DAYS = int(os.getenv("METADATA_CACHE_EXPIRY_DAYS", 30))


# ---------- Normalization ----------
def normalize_title(title: str) -> str:
    """
    Normalize a title for consistent lookup.
    - Lowercase
    - Remove punctuation (keep letters, digits, spaces)
    - Collapse spaces and strip
    """
    if not title:
        return ""
    normalized = re.sub(r"[^\w\s]", " ", title.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


# ---------- Core functions ----------
def find_by_title(
    title: str,
    content_type: Optional[str] = None,  # kept for API compatibility
    year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached metadata by normalized title.

    If the cached record is older than CACHE_EXPIRY_DAYS, it is considered
    stale and treated as a cache miss (returns None).

    Args:
        title: The title to search for.
        content_type: Optional filter (ignored for TMDBMovie, kept for compatibility).
        year: Optional year filter (matches release_date__year).

    Returns:
        Optional[Dict[str, Any]]: Metadata dict or None.
    """
    normalized = normalize_title(title)
    logger.debug(f"Searching TMDB cache for '{title}' (normalized='{normalized}')")

    queryset = TMDBMovie.objects.filter(title_normalized=normalized)
    if year is not None:
        queryset = queryset.filter(release_date__year=year)

    movie = queryset.order_by("-vote_average").first()
    if not movie:
        logger.info(f"Cache miss: '{title}' not found in TMDB")
        return None

    # ---- Staleness check ----
    now = timezone.now()
    if movie.last_updated and (now - movie.last_updated).days > CACHE_EXPIRY_DAYS:
        logger.info(
            f"Cache stale for '{title}' (updated at {movie.last_updated}, "
            f"older than {CACHE_EXPIRY_DAYS} days). Treating as miss."
        )
        return None

    logger.info(f"Cache hit: found '{movie.title}' (ID {movie.tmdb_id})")

    # Convert to unified metadata dict (common schema)
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
        "content_type": "movie",  # could be extended with a field
        "season_count": None,
        "episode_count": None,
    }


def find_by_external_id(external_id: str, source: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached content by provider ID and source (generic).
    For TMDB, external_id is tmdb_id and source is "tmdb".
    """
    if source.lower() != "tmdb":
        logger.warning(f"Only 'tmdb' source is supported; got '{source}'")
        return None
    try:
        movie = TMDBMovie.objects.get(tmdb_id=external_id)
        # Reuse conversion via find_by_title (which also checks staleness)
        return find_by_title(movie.title)
    except ObjectDoesNotExist:
        logger.info(f"Cache miss: external_id='{external_id}', source='{source}'")
        return None


def find_by_telegram_file_id(telegram_file_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached metadata by Telegram file ID.

    This is a placeholder – the TelegramFile model is not implemented in this
    project, so this function always returns None.
    """
    logger.warning(
        f"find_by_telegram_file_id called with '{telegram_file_id}' – "
        "TelegramFile model not available. Returning None."
    )
    return None


@transaction.atomic
def save_metadata(
    data: Dict[str, Any],
    telegram_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Save (upsert) metadata into TMDBMovie.

    If a movie with the same tmdb_id exists, it is updated.

    Args:
        data: Metadata dict (must contain "external_id" for tmdb_id).
        telegram_file_id: Optional unique Telegram file ID (ignored, kept for
                          API compatibility with manager.py).

    Returns:
        Dict[str, Any]: The saved metadata dict.

    Raises:
        ValueError: If external_id is missing.
    """
    if "external_id" not in data:
        raise ValueError("Missing 'external_id' in metadata data")

    tmdb_id = data["external_id"]
    title = data.get("title", "")
    normalized = normalize_title(title)

    logger.info(f"Saving metadata for tmdb_id={tmdb_id}")

    # Build defaults with safe field mapping
    defaults = {
        "title": title,
        "title_normalized": normalized,
        "poster_path": data.get("poster", ""),
        "backdrop_path": data.get("backdrop", ""),
        "overview": data.get("overview", ""),
        "genres": ",".join(data.get("genres", [])) if isinstance(data.get("genres"), list) else data.get("genres", ""),
        "release_date": data.get("release_date"),
        "vote_average": data.get("rating", 0.0),
        "original_title": data.get("original_title", ""),
        "original_language": data.get("language", ""),
        "runtime": data.get("runtime"),
        "status": data.get("status", ""),
    }

    # Remove keys that don't exist on the model (safety)
    model_fields = {f.name for f in TMDBMovie._meta.get_fields()}
    defaults = {k: v for k, v in defaults.items() if k in model_fields}

    movie, created = TMDBMovie.objects.update_or_create(
        tmdb_id=tmdb_id,
        defaults=defaults,
    )
    logger.debug(f"TMDBMovie {'created' if created else 'updated'} (ID {movie.id})")

    if telegram_file_id:
        logger.debug(f"Telegram file ID '{telegram_file_id}' provided – no linking performed (model not available).")

    # Return the metadata dict
    return find_by_title(movie.title) or {}


@transaction.atomic
def update_metadata(
    external_id: str,
    source: str,
    data: Dict[str, Any],
    telegram_file_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update an existing metadata record identified by external_id and source.

    If the record does not exist, logs a warning and returns None.

    Args:
        external_id: Provider‑specific ID (e.g., tmdb_id).
        source: Provider name ("tmdb").
        data: Fields to update.
        telegram_file_id: Optional Telegram file ID (ignored).

    Returns:
        Optional[Dict[str, Any]]: Updated metadata dict, or None if not found.
    """
    if source.lower() != "tmdb":
        logger.warning(f"Only 'tmdb' source is supported; got '{source}'")
        return None

    try:
        movie = TMDBMovie.objects.get(tmdb_id=external_id)
    except ObjectDoesNotExist:
        logger.warning(f"Update failed: no movie with tmdb_id='{external_id}'")
        return None

    # Apply updates (skip external_id, source)
    for key, value in data.items():
        if key in ("external_id", "source"):
            continue
        # Map common keys to model fields
        field_mapping = {
            "poster": "poster_path",
            "backdrop": "backdrop_path",
            "rating": "vote_average",
            "language": "original_language",
        }
        model_field = field_mapping.get(key, key)
        if hasattr(movie, model_field):
            setattr(movie, model_field, value)

    if "title" in data and data["title"]:
        movie.title_normalized = normalize_title(data["title"])

    movie.save()
    logger.info(f"Updated movie tmdb_id='{external_id}'")

    if telegram_file_id:
        logger.debug(f"Telegram file ID '{telegram_file_id}' provided – no linking performed.")

    return find_by_title(movie.title)


@transaction.atomic
def delete_metadata(external_id: str, source: str) -> bool:
    """
    Delete a cached metadata entry by external_id and source.
    Returns True if deletion succeeded (or entry didn't exist), False if error.
    """
    if source.lower() != "tmdb":
        logger.warning(f"Only 'tmdb' source is supported; got '{source}'")
        return False

    try:
        count, _ = TMDBMovie.objects.filter(tmdb_id=external_id).delete()
        if count:
            logger.info(f"Deleted metadata for tmdb_id='{external_id}'")
        else:
            logger.info(f"No metadata found to delete for tmdb_id='{external_id}'")
        return True
    except Exception as e:
        logger.error(f"Error deleting metadata: {e}")
        return False

