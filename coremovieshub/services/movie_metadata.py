import logging
from coremovieshub.models import TMDBMovie
import re

logger = logging.getLogger(__name__)
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


def _normalize_title(title):
    """
    Normalize a title for better matching:
    - Strip whitespace
    - Collapse multiple spaces
    - Optionally remove common stop words (e.g., 'The', 'A', 'An') at the start
    """
    if not title:
        return ""
    title = " ".join(title.split())          # collapse spaces
    # Remove leading articles (case-insensitive) – useful for exact matches
    # e.g., "The Last of Us" -> "Last of Us"
    # This is optional; you can comment out if it causes false matches.
    title = re.sub(r"^(the|a|an)\s+", "", title, flags=re.I)
    return title.strip()


def search_movie_metadata(title, year=None):
    """
    Search for a movie in the local TMDB cache.
    Uses a progressive search strategy:
    1. Exact normalized match (case-insensitive)
    2. Contains match (case-insensitive)
    3. Loose match using the first part of the title (before separators)
    """
    if not title:
        return None

    title = title.strip()
    normalized_title = _normalize_title(title)

    # 1. Exact normalized match
    queryset = TMDBMovie.objects.filter(title__iexact=normalized_title)
    if year:
        queryset = queryset.filter(release_date__year=year)

    movie = queryset.first()
    if movie:
        logger.info(f"TMDB Exact match: '{normalized_title}' ({year}) -> {movie}")
        return _build_movie_dict(movie)

    # 2. Contains match
    queryset = TMDBMovie.objects.filter(title__icontains=normalized_title)
    if year:
        queryset = queryset.filter(release_date__year=year)
    # Prefer most recent release
    movie = queryset.order_by("-release_date").first()
    if movie:
        logger.info(f"TMDB Contains match: '{normalized_title}' ({year}) -> {movie}")
        return _build_movie_dict(movie)

    # 3. Loose match: try the first segment before separators like " - ", ":", "|"
    # This helps when titles have subtitles or extra info not removed.
    loose_title = title.split(" - ")[0].split(":")[0].split("|")[0].strip()
    if loose_title and loose_title != title:
        queryset = TMDBMovie.objects.filter(title__icontains=loose_title)
        if year:
            queryset = queryset.filter(release_date__year=year)
        movie = queryset.order_by("-release_date").first()
        if movie:
            logger.info(f"TMDB Loose match: '{loose_title}' ({year}) -> {movie}")
            return _build_movie_dict(movie)

    # 4. Fallback: search by all significant words (split on spaces) – optional
    # For a more aggressive approach, you could use trigram similarity (PostgreSQL).
    # Example (if using pg_trgm):
    # from django.contrib.postgres.search import TrigramSimilarity
    # queryset = TMDBMovie.objects.annotate(similarity=TrigramSimilarity('title', normalized_title)) \
    #             .filter(similarity__gt=0.3) \
    #             .order_by('-similarity')
    # if year: queryset = queryset.filter(release_date__year=year)
    # movie = queryset.first()

    logger.warning(f"No match found for '{title}' ({year})")
    return None


def _build_movie_dict(movie):
    """Build the standard metadata dictionary from a TMDBMovie instance."""
    return {
        "tmdb_id": movie.tmdb_id,
        "poster": (
            f"{TMDB_IMAGE_BASE}/w500{movie.poster_path}"
            if movie.poster_path
            else None
        ),
        "banner": (
            f"{TMDB_IMAGE_BASE}/original{movie.backdrop_path}"
            if movie.backdrop_path
            else None
        ),
        "overview": movie.overview,
        "rating": movie.vote_average,
        "release_date": movie.release_date,
        "duration": movie.runtime,
        "tags": movie.genres,
        "season_count": movie.number_of_seasons,
        "episode_count": movie.number_of_episodes,
        "status": movie.status,
    }