from coremovieshub.models import TMDBMovie

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

def search_movie_metadata(title):

    if not title:
        return None

    title = title.strip()

    movie = (
        TMDBMovie.objects
        .filter(title__iexact=title)
        .first()
    )
    
    print(f"TMDB Exact Search: {title} -> {movie}")

    if not movie:
        movie = (
            TMDBMovie.objects
            .filter(title__icontains=title)
            .order_by("-release_date")
            .first()
        )
        
        print(f"TMDB Contains Search: {title} -> {movie}")

    if not movie:
        return None

    return {
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

        "overview": movie.overview or "",

        "rating": movie.vote_average,

        "release_date": movie.release_date,
    }