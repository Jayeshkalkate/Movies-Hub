# movie_metadata.py
"""
Metadata retrieval and application service for movies using locally cached TMDb data.

Provides:
- search_movie_metadata(title, year=None) → dict or None
- apply_metadata_to_movie(movie_instance, title, year=None) → bool
"""

import logging
import difflib
from datetime import datetime

from django.utils.text import slugify
from django.db.models import Q

from coremovieshub.models import TMDBMovie
from metadata.providers.tmdb import get_tmdb_client
from metadata.tmdb_cache import find_by_title, save_metadata   # <-- added

logger = logging.getLogger(__name__)

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


def search_movie_metadata(title, year=None):
    """
    Search for movie metadata in local TMDBMovie cache, with automatic refresh
    if cached data is stale (> CACHE_EXPIRY_DAYS days old).

    Returns a dict with the following keys, or None if no match:
        - tmdb_id
        - poster (full URL)
        - banner (full URL)
        - overview
        - rating (float)
        - release_date (date object)
        - runtime (int, in minutes)
        - original_title
        - original_language
        - genres (list of strings)
        - status (string)
        - confidence_score (float 0-1)

    Args:
        title (str): movie title to search for
        year (int, optional): release year to narrow results

    Returns:
        dict or None
    """
    if not title:
        return None

    title = " ".join(title.split())  # normalise spacing
    normalized_title = slugify(title)

    def similarity(a, b):
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def score_movie(m, search_title, search_year):
        s = 0.0
        # Title similarity
        s += similarity(search_title, m.title) * 0.4
        # Year match
        if m.release_date and search_year:
            if m.release_date.year == search_year:
                s += 0.3
            elif abs(m.release_date.year - search_year) <= 1:
                s += 0.15
        # Popularity (vote_average normalized to 0-1)
        if m.vote_average:
            s += (m.vote_average / 10) * 0.3
        return s

    movie = None

    # ----- STEP 1: Use the unified cache lookup (with staleness check) -----
    cached = find_by_title(title, year=year)
    if cached:
        # We have a valid, fresh cache entry. Build metadata from it.
        # We'll still compute a confidence score based on the movie instance.
        # But we need the actual movie instance to get additional fields like genres.
        # So we retrieve it from the DB using the tmdb_id.
        try:
            movie = TMDBMovie.objects.get(tmdb_id=cached["external_id"])
            movie._score = 1.0  # high confidence because it was an exact normalized match
        except TMDBMovie.DoesNotExist:
            # Should not happen, but fallback to using cached dict directly
            movie = None
            # We can construct a metadata dict directly from cached data
            return {
                "tmdb_id": cached["external_id"],
                "poster": cached["poster"],
                "banner": cached["backdrop"],
                "overview": cached["overview"],
                "rating": cached["rating"],
                "release_date": cached["release_date"],
                "runtime": cached["runtime"],
                "duration": cached["runtime"],
                "original_title": cached["original_title"],
                "original_language": cached["language"],
                "genres": cached["genres"],  # list
                "status": cached["status"],
                "confidence_score": 1.0,
            }
    # If no fresh cache entry, proceed to traditional queries
    # (they may return stale entries but we will also add a staleness check below)

    # 1. Exact title + year
    if not movie and year:
        candidates = TMDBMovie.objects.filter(
            title_normalized=normalized_title,
            release_date__year=year,
        ).order_by("-vote_average")
        if candidates.exists():
            movie = candidates.first()
            movie._score = score_movie(movie, title, year)
            logger.info(
                "TMDB Exact Title+Year match: %s (%s) score=%.2f",
                movie.title, year, movie._score
            )

    # 2. Exact title only
    if not movie:
        candidates = TMDBMovie.objects.filter(
            title_normalized=normalized_title
        ).order_by("-vote_average")
        if candidates.exists():
            best = None
            best_score = -1.0
            for m in candidates:
                sc = score_movie(m, title, year)
                if sc > best_score:
                    best_score = sc
                    best = m
            movie = best
            if movie:
                movie._score = best_score
                logger.info(
                    "TMDB Exact Title match: %s (%s) score=%.2f",
                    movie.title, year, movie._score
                )

    # 3. Similarity-based (≥0.80) – use prefix filter to reduce scan
    if not movie:
        prefix = normalized_title[:8]
        qs = TMDBMovie.objects.filter(
            Q(title_normalized__startswith=prefix)
        )
        if year:
            qs = qs.filter(release_date__year=year)

        if not qs.exists() and year:
            qs = TMDBMovie.objects.filter(release_date__year=year)
        elif not qs.exists():
            qs = TMDBMovie.objects.all()

        best = None
        best_score = -1.0
        for candidate in qs.iterator():
            ratio = similarity(title, candidate.title)
            if ratio >= 0.80:
                sc = ratio * 0.4 + score_movie(candidate, title, year) * 0.6
                if sc > best_score:
                    best_score = sc
                    best = candidate
        movie = best
        if movie:
            movie._score = best_score
            logger.info(
                "TMDB Similarity match: %s (%s) score=%.2f",
                movie.title, year, movie._score
            )

    # ----- Staleness check for any found movie -----
    if movie:
        # If the movie is stale, we ignore it and trigger a fresh fetch
        from metadata.tmdb_cache import CACHE_EXPIRY_DAYS
        from django.utils import timezone
        if movie.last_updated and (timezone.now() - movie.last_updated).days > CACHE_EXPIRY_DAYS:
            logger.info(
                f"Found movie '{movie.title}' but cache is stale (updated {movie.last_updated}). "
                "Refreshing from TMDB."
            )
            movie = None  # treat as miss

    # ========== Cache miss or stale → fetch from TMDB API ==========
    if not movie:
        logger.info(
            "Cache miss (or stale) for '%s'. Fetching from TMDB...",
            title,
        )

        try:
            client = get_tmdb_client()

            # Search with the provided title and year
            response = client.search_movie(
                title,
                year=year,
            )

            results = response.get("results", [])

            if not results:
                logger.info("TMDB returned no results.")
                return None

            # Get full details for the best match
            details = client.get_movie(results[0]["id"])

            # Parse release_date
            release_date = None
            if details.get("release_date"):
                try:
                    release_date = datetime.strptime(
                        details["release_date"],
                        "%Y-%m-%d",
                    ).date()
                except ValueError:
                    pass

            # Prepare metadata dict in the unified schema used by save_metadata
            metadata = {
                "external_id": details["id"],
                "title": details.get("title") or "",
                "overview": details.get("overview") or "",
                "poster": details.get("poster_path") or "",
                "backdrop": details.get("backdrop_path") or "",
                "genres": [g["name"] for g in details.get("genres", [])],
                "release_date": release_date.isoformat() if release_date else None,
                "rating": details.get("vote_average"),
                "runtime": details.get("runtime"),
                "status": details.get("status") or "",
                "original_title": details.get("original_title") or "",
                "language": details.get("original_language") or "",
            }

            # Save to cache (this will also update the updated_at timestamp)
            saved = save_metadata(metadata)
            # Retrieve the movie instance for building the final metadata dict
            movie = TMDBMovie.objects.get(tmdb_id=details["id"])
            movie._score = 1.0  # fresh fetch is most accurate

            logger.info(
                "Fetched and saved TMDB movie: %s (%s)",
                movie.title, movie.release_date.year if movie.release_date else "N/A"
            )

        except Exception as e:
            logger.exception("TMDB fetch failed: %s", e)
            return None

    # ----- Continue with the existing code to build metadata dict -----
    # (movie is now guaranteed to be an instance, either from cache or newly fetched)

    # ----- Strict year validation (optional) -----
    if year and movie.release_date:
        if movie.release_date.year != year:
            logger.debug("Year mismatch, discarding match for %s", movie.title)
            return None

    # ----- Build metadata dict with safe conversions -----
    poster = None
    if movie.poster_path:
        poster = f"{TMDB_IMAGE_BASE}/w500{movie.poster_path}"

    banner = None
    if movie.backdrop_path:
        banner = f"{TMDB_IMAGE_BASE}/w1280{movie.backdrop_path}"

    rating = None
    if movie.vote_average is not None:
        try:
            rating = float(movie.vote_average)
        except (TypeError, ValueError):
            rating = None

    release_date = movie.release_date  # already a date or None

    runtime = None
    if movie.runtime is not None:
        try:
            runtime = int(movie.runtime)
        except (TypeError, ValueError):
            runtime = None

    # Genres: convert comma-separated string to list
    genres = []
    if movie.genres:
        genres = [g.strip() for g in movie.genres.split(",") if g.strip()]

    metadata = {
        "tmdb_id": movie.tmdb_id,
        "poster": poster,
        "banner": banner,
        "overview": movie.overview,
        "rating": rating,
        "release_date": release_date,
        "runtime": runtime,
        "duration": runtime,
        "original_title": movie.original_title,
        "original_language": movie.original_language,
        "genres": genres,
        "status": movie.status,
        "confidence_score": getattr(movie, '_score', 0.0),
    }
    return metadata


def apply_metadata_to_movie(movie_instance, title, year=None):
    """
    Search for metadata and apply it directly to a movie instance,
    then save only the updated fields.

    Args:
        movie_instance: A Django model instance (e.g., TelegramMovie)
                        with fields: tmdb_id, poster, banner, overview,
                        rating, release_date, duration, genres,
                        original_title, original_language, status.
        title (str): movie title to search for
        year (int, optional): release year

    Returns:
        bool: True if metadata was found and applied, False otherwise.
    """
    metadata = search_movie_metadata(title, year)
    if not metadata:
        return False

    # Map metadata keys to model field names (adjust if your model uses different names)
    field_mapping = {
        "tmdb_id": "tmdb_id",
        "poster": "poster",
        "banner": "banner",
        "overview": "overview",
        "rating": "rating",
        "release_date": "release_date",
        "duration": "duration",
        "runtime": "runtime",
        "original_title": "original_title",
        "original_language": "original_language",
        "genres": "genres",
        "status": "status",
    }

    updated_fields = []
    for meta_key, field_name in field_mapping.items():
        if meta_key in metadata and hasattr(movie_instance, field_name):
            value = metadata[meta_key]
            if getattr(movie_instance, field_name) != value:
                setattr(movie_instance, field_name, value)
                updated_fields.append(field_name)

    if updated_fields:
        movie_instance.save(update_fields=updated_fields)
        logger.info(
            "Applied metadata to %s (updated: %s)",
            movie_instance, ", ".join(updated_fields)
        )
    else:
        logger.debug("No changes needed for %s", movie_instance)

    return True

