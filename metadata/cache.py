"""
Cache layer for metadata using Django ORM.

This module provides functions to interact with the Django database for caching
metadata from external providers. It does NOT call any external APIs.

It provides:
    - find_by_title: retrieve cached content by title (with optional type/year)
    - find_by_external_id: retrieve cached content by provider ID and source
    - save_metadata: upsert (create or update) metadata from a dict
    - update_metadata: update an existing record by external_id and source

All operations use database transactions and include comprehensive logging.

The model used is configurable via Django settings:
    CACHE_MODEL_APP   - app label (default: "coremovieshub")
    CACHE_MODEL_NAME  - model name (default: "CachedContent")
"""

import logging
import re
from typing import Dict, Any, Optional, List, Type

from django.apps import apps
from django.db import transaction, models
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings

# Module logger
logger = logging.getLogger(__name__)

# Default model configuration (can be overridden in Django settings)
DEFAULT_APP = "coremovieshub"
DEFAULT_MODEL = "CachedContent"


def _get_cache_model() -> Type[models.Model]:
    """
    Retrieve the cache model class from Django apps.

    The app and model names can be overridden via settings:
        - CACHE_MODEL_APP (default: "coremovieshub")
        - CACHE_MODEL_NAME (default: "CachedContent")

    Returns:
        models.Model: The cache model class.

    Raises:
        LookupError: If the model is not found.
    """
    app_label = getattr(settings, "CACHE_MODEL_APP", DEFAULT_APP)
    model_name = getattr(settings, "CACHE_MODEL_NAME", DEFAULT_MODEL)
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Could not find model {app_label}.{model_name}: {e}")
        raise


def _normalize_title(title: str) -> str:
    """
    Normalize a title for consistent lookup.

    - Convert to lowercase
    - Remove all punctuation (keep letters, digits, spaces)
    - Collapse multiple spaces into one
    - Strip leading/trailing whitespace

    Example: "Spider-Man: Across the Spider-Verse" -> "spider man across the spider verse"
    """
    if not title:
        return ""
    # Lowercase
    normalized = title.lower()
    # Remove punctuation (keep letters, digits, spaces)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _model_to_dict(instance: models.Model) -> Dict[str, Any]:
    """
    Convert a cache model instance into the common metadata schema dict.

    Args:
        instance: A cache model instance.

    Returns:
        Dict[str, Any]: Metadata in common schema.
    """
    return {
        "external_id": instance.external_id,
        "source": instance.source,
        "title": instance.title,
        "original_title": instance.original_title,
        "overview": instance.overview,
        "poster": instance.poster,
        "backdrop": instance.backdrop,
        "genres": instance.genres or [],
        "release_date": instance.release_date,
        "rating": instance.rating,
        "language": instance.language,
        "runtime": instance.runtime,
        "status": instance.status,
        "content_type": instance.content_type,
        "season_count": instance.season_count,
        "episode_count": instance.episode_count,
    }


def find_by_title(
    title: str,
    content_type: Optional[str] = None,
    year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Search the cache for content by title (case‑insensitive, with normalisation).

    Optionally filter by content_type and year (from release_date).

    Args:
        title: The title to search for.
        content_type: Optional filter, e.g., "movie" or "tv".
        year: Optional filter, matches year from release_date.

    Returns:
        Optional[Dict[str, Any]]: The cached metadata dict if found, else None.
    """
    CacheModel = _get_cache_model()
    normalized = _normalize_title(title)
    logger.debug(f"Searching cache for title='{title}' (normalized='{normalized}'), type={content_type}, year={year}")

    # Build queryset – use normalized_title for accurate matching
    queryset = CacheModel.objects.filter(normalized_title=normalized)

    if content_type:
        queryset = queryset.filter(content_type=content_type)

    if year is not None:
        # release_date is a DateField or CharField; assume DateField and extract year
        queryset = queryset.filter(release_date__year=year)

    # Return the first match (order by rating descending, or latest?)
    instance = queryset.order_by("-rating", "-release_date").first()

    if instance:
        logger.info(f"Cache hit: found '{title}' with external_id={instance.external_id}")
        return _model_to_dict(instance)
    else:
        logger.info(f"Cache miss: title '{title}' not found")
        return None


def find_by_external_id(external_id: str, source: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached content by external provider ID and source.

    Args:
        external_id: The provider's unique ID (string).
        source: The provider name (e.g., "tmdb", "tvmaze", "jikan", "anilist").

    Returns:
        Optional[Dict[str, Any]]: The cached metadata dict if found, else None.
    """
    CacheModel = _get_cache_model()
    logger.debug(f"Searching cache for external_id='{external_id}', source='{source}'")

    try:
        instance = CacheModel.objects.get(external_id=external_id, source=source)
        logger.info(f"Cache hit: external_id={external_id}, source={source}")
        return _model_to_dict(instance)
    except ObjectDoesNotExist:
        logger.info(f"Cache miss: external_id={external_id}, source={source}")
        return None


@transaction.atomic
def save_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save (upsert) metadata into the cache.

    If a record with the same external_id and source exists, it is updated.
    Otherwise, a new record is created.

    The `normalized_title` field is automatically computed from the `title`.

    Args:
        data: Metadata dict in the common schema.

    Returns:
        Dict[str, Any]: The saved metadata dict (from the updated/created instance).

    Raises:
        ValueError: If required fields are missing.
    """
    CacheModel = _get_cache_model()

    # Validate required fields
    required_fields = ["external_id", "source", "title"]
    for field in required_fields:
        if not data.get(field):
            raise ValueError(f"Missing required field '{field}' in metadata data")

    external_id = data["external_id"]
    source = data["source"]
    title = data["title"]

    # Compute normalized title
    normalized_title = _normalize_title(title)

    logger.info(f"Saving metadata: external_id='{external_id}', source='{source}'")

    # Try to get existing record
    try:
        instance = CacheModel.objects.get(external_id=external_id, source=source)
        logger.debug(f"Updating existing record (ID {instance.pk})")
        # Update fields (except pk, external_id, source, which are used as lookup)
        for key, value in data.items():
            if key not in ("external_id", "source"):
                setattr(instance, key, value)
        instance.normalized_title = normalized_title
        instance.save()
    except ObjectDoesNotExist:
        logger.debug(f"Creating new record for external_id='{external_id}', source='{source}'")
        # Add normalized_title to data before creation
        data["normalized_title"] = normalized_title
        instance = CacheModel(**data)
        instance.save()

    logger.info(f"Metadata saved successfully (ID {instance.pk})")
    return _model_to_dict(instance)


@transaction.atomic
def update_metadata(
    external_id: str,
    source: str,
    data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Update an existing metadata record identified by external_id and source.

    If the record does not exist, logs a warning and returns None.

    Also updates the `normalized_title` if `title` is included in `data`.

    Args:
        external_id: The provider's unique ID.
        source: The provider name.
        data: Dictionary of fields to update (partial update).

    Returns:
        Optional[Dict[str, Any]]: The updated metadata dict if updated, else None.
    """
    CacheModel = _get_cache_model()

    logger.debug(f"Updating metadata: external_id='{external_id}', source='{source}'")

    try:
        instance = CacheModel.objects.get(external_id=external_id, source=source)
    except ObjectDoesNotExist:
        logger.warning(f"Update failed: no record found for external_id='{external_id}', source='{source}'")
        return None

    # Apply updates (skip external_id and source)
    for key, value in data.items():
        if key not in ("external_id", "source"):
            setattr(instance, key, value)

    # Recompute normalized_title if title was updated
    if "title" in data and data["title"]:
        instance.normalized_title = _normalize_title(data["title"])

    instance.save()
    logger.info(f"Updated metadata for external_id='{external_id}', source='{source}' (ID {instance.pk})")
    return _model_to_dict(instance)


# ------------------- Suggested Django Model Definition -------------------
#
# To use this cache layer, create a model in your app (e.g., coremovieshub/models.py):
#
# from django.db import models
#
# class CachedContent(models.Model):
#     external_id = models.CharField(max_length=100, db_index=True)
#     source = models.CharField(max_length=50, db_index=True)  # tmdb, tvmaze, jikan, anilist
#     normalized_title = models.CharField(max_length=500, db_index=True)
#     title = models.CharField(max_length=500)
#     original_title = models.CharField(max_length=500, blank=True)
#     overview = models.TextField(blank=True)
#     poster = models.URLField(max_length=500, blank=True)
#     backdrop = models.URLField(max_length=500, blank=True)
#     genres = models.JSONField(default=list)
#     release_date = models.DateField(null=True, blank=True)
#     rating = models.FloatField(default=0.0)
#     language = models.CharField(max_length=20, blank=True)
#     runtime = models.IntegerField(null=True, blank=True)
#     status = models.CharField(max_length=50, blank=True)
#     content_type = models.CharField(max_length=20, db_index=True)  # movie, tv
#     season_count = models.IntegerField(null=True, blank=True)
#     episode_count = models.IntegerField(null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#
#     class Meta:
#         unique_together = [["external_id", "source"]]
#         indexes = [
#             models.Index(fields=["normalized_title", "content_type"]),
#         ]
#
#     def __str__(self):
#         return f"{self.title} ({self.source})"
#
# Then set in settings:
# CACHE_MODEL_APP = "coremovieshub"
# CACHE_MODEL_NAME = "CachedContent"

# ------------------- Example usage (for documentation) -------------------
if __name__ == "__main__":
    # This is a placeholder; actual usage would be in a Django environment.
    pass