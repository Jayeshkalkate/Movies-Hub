from coremovieshub.models import TMDBMovie
from django.utils.text import slugify

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

def search_movie_metadata(title, year=None):

    if not title:
        return None

    title = title.strip()

    normalized_title = slugify(title)
    
    queryset = TMDBMovie.objects.filter(
        title_normalized=normalized_title
    )
    
    if year:
        queryset = queryset.filter(
            release_date__year=year
        )
        
    movie = queryset.first()
        
    print(
        f"TMDB Exact Search: {title} ({year}) -> {movie}"
    )

    if not movie:
        queryset = TMDBMovie.objects.filter(
            title_normalized__startswith=normalized_title
        )
        
        if year:
            queryset = queryset.filter(
                release_date__year=year
            )
        
        movie = queryset.order_by(
            "-release_date"
        ).first()
        
        print(
            f"TMDB Contains Search: {title} ({year}) -> {movie}"
        )

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