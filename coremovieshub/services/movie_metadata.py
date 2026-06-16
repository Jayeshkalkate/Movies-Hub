from coremovieshub.models import TMDBMovie
from django.utils.text import slugify

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

def search_movie_metadata(title, year=None):
    if not title:
        return None

    title = title.strip()
    normalized_title = slugify(title)
    movie = None

    # 1. Highest priority: exact title + year
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

    # 2. Exact title only (if year search failed)
    if not movie:
        movie = (
            TMDBMovie.objects.filter(title_normalized=normalized_title)
            .order_by("-vote_average")
            .first()
        )
        print(f"TMDB Exact Title Search: {title} ({year}) -> {movie}")

    # 3. Partial title + year (e.g., "Avatar" matches "Avatar: The Way of Water" with same year)
    if not movie and year:
        movie = (
            TMDBMovie.objects.filter(
                title_normalized__startswith=normalized_title,
                release_date__year=year,
            )
            .order_by("-vote_average")
            .first()
        )
        print(f"TMDB Partial Title+Year Search: {title} ({year}) -> {movie}")

    # 4. Last fallback: partial title only
    if not movie:
        movie = (
            TMDBMovie.objects.filter(title_normalized__startswith=normalized_title)
            .order_by("-vote_average")
            .first()
        )
        print(f"TMDB Partial Title Search: {title} ({year}) -> {movie}")

    if not movie:
        return None

    metadata = {
        "tmdb_id": movie.tmdb_id,
        "poster": f"{TMDB_IMAGE_BASE}/w500{movie.poster_path}" if movie.poster_path else None,
        "banner": f"{TMDB_IMAGE_BASE}/w1280{movie.backdrop_path}" if movie.backdrop_path else None,
        "overview": movie.overview,
        "rating": movie.vote_average,
        "release_date": movie.release_date,
    }

    # ---- YEAR VALIDATION (fix for false positives) ----
    if year and metadata.get("release_date"):
        release_year = metadata["release_date"].year
        if abs(release_year - year) > 1:
            return None

    return metadata

