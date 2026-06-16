from coremovieshub.models import TMDBMovie

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

def search_movie_metadata(title, year=None):

    if not title:
        return None

    title = title.strip()

    queryset = TMDBMovie.objects.filter(
        title__iexact=title
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
            title__icontains=title
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