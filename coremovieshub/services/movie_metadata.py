from coremovieshub.models import TMDBMovie


TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


def search_movie_metadata(title):
    """
    Search TMDB metadata from PostgreSQL.

    Returns:
        dict | None
    """

    if not title:
        return None

    title = title.strip()

    # --------------------------------------------------
    # Exact match
    # --------------------------------------------------
    movie = (
        TMDBMovie.objects
        .filter(
            title__iexact=title
        )
        .first()
    )

    # --------------------------------------------------
    # Partial match fallback
    # --------------------------------------------------
    if not movie:
        movie = (
            TMDBMovie.objects
            .filter(
                title__icontains=title
            )
            .first()
        )

    if not movie:
        return None

    return {
        "poster": (
            f"{TMDB_IMAGE_BASE}/w500"
            f"{movie.poster_path}"
            if movie.poster_path
            else ""
        ),

        "banner": (
            f"{TMDB_IMAGE_BASE}/original"
            f"{movie.backdrop_path}"
            if movie.backdrop_path
            else ""
        ),

        "overview": (
            movie.overview
            or ""
        ),

        "rating": (
            float(movie.vote_average)
            if movie.vote_average is not None
            else None
        ),

        "release_date": (
            movie.release_date
        ),
    }