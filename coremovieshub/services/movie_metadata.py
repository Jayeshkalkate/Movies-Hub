from coremovieshub.models import TMDBMovie
from django.utils.text import slugify
import difflib

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

def search_movie_metadata(title, year=None):
    if not title:
        return None

    title = title.strip()
    normalized_title = slugify(title)
    movie = None

    # Helper to compute similarity ratio (case‑insensitive)
    def similarity(a, b):
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

    # 1. Highest priority: exact title + exact year
    if year:
        movie = (
            TMDBMovie.objects.filter(
                title_normalized=normalized_title,
                release_date__year=year,
            )
            .order_by("-vote_average")
            .first()
        )
        print(f"TMDB Exact Title+Year Search: {title} ({year}) -> {movie}")

    # 2. Exact title only (if year search failed or no year given)
    if not movie:
        movie = (
            TMDBMovie.objects.filter(title_normalized=normalized_title)
            .order_by("-vote_average")
            .first()
        )
        print(f"TMDB Exact Title Search: {title} ({year}) -> {movie}")

    # 3. If still no match, try similarity-based search (≥ 0.9)
    if not movie:
        # Build a candidate queryset – filter by year if provided, else all
        if year:
            candidates = TMDBMovie.objects.filter(release_date__year=year)
        else:
            candidates = TMDBMovie.objects.all()

        best_match = None
        best_ratio = 0.0
        for candidate in candidates:
            # Use the original title (not the slug) for comparison
            ratio = similarity(title, candidate.title)
            if ratio >= 0.9 and ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate

        if best_match:
            movie = best_match
            print(f"TMDB Similarity Search: {title} ({year}) -> {movie} (ratio={best_ratio:.2f})")

    # 4. If still no movie, reject (no partial/prefix fallback)
    if not movie:
        print(f"TMDB No match found for: {title} ({year})")
        return None

    metadata = {
        "tmdb_id": movie.tmdb_id,
        "poster": f"{TMDB_IMAGE_BASE}/w500{movie.poster_path}" if movie.poster_path else None,
        "banner": f"{TMDB_IMAGE_BASE}/w1280{movie.backdrop_path}" if movie.backdrop_path else None,
        "overview": movie.overview,
        "rating": movie.vote_average,
        "release_date": movie.release_date,
    }

    # ---- YEAR VALIDATION (strict) ----
    if year and metadata.get("release_date"):
        release_year = metadata["release_date"].year
        if release_year != year:
            # Mismatch – reject
            return None

    return metadata

