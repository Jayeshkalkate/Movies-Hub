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

    def similarity(a, b):
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

    # Helper to score a movie
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

    # 1. Exact title + year
    if year:
        candidates = TMDBMovie.objects.filter(
            title_normalized=normalized_title,
            release_date__year=year,
        ).order_by("-vote_average")
        if candidates.exists():
            movie = candidates.first()
            # Compute score
            movie._score = score_movie(movie, title, year)
            print(f"TMDB Exact Title+Year Search: {title} ({year}) -> {movie} score={movie._score:.2f}")

    # 2. Exact title only
    if not movie:
        candidates = TMDBMovie.objects.filter(
            title_normalized=normalized_title
        ).order_by("-vote_average")
        if candidates.exists():
            # Pick the one with highest score (including year check)
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
                print(f"TMDB Exact Title Search: {title} ({year}) -> {movie} score={movie._score:.2f}")

    # 3. Similarity-based (≥0.9) with scoring
    if not movie:
        if year:
            candidates = TMDBMovie.objects.filter(release_date__year=year)
        else:
            candidates = TMDBMovie.objects.all()

        best = None
        best_score = -1.0
        for candidate in candidates:
            ratio = similarity(title, candidate.title)
            if ratio >= 0.9:
                sc = ratio * 0.4 + score_movie(candidate, title, year) * 0.6
                if sc > best_score:
                    best_score = sc
                    best = candidate
        movie = best
        if movie:
            movie._score = best_score
            print(f"TMDB Similarity Search: {title} ({year}) -> {movie} score={movie._score:.2f}")

    if not movie:
        print(f"TMDB No match found for: {title} ({year})")
        return None

    # Year validation (strict) – keep as before
    if year and movie.release_date:
        if movie.release_date.year != year:
            return None

    metadata = {
        "tmdb_id": movie.tmdb_id,
        "poster": f"{TMDB_IMAGE_BASE}/w500{movie.poster_path}" if movie.poster_path else None,
        "banner": f"{TMDB_IMAGE_BASE}/w1280{movie.backdrop_path}" if movie.backdrop_path else None,
        "overview": movie.overview,
        "rating": movie.vote_average,
        "release_date": movie.release_date,
        "confidence_score": getattr(movie, '_score', 0.0),   # include score
    }
    return metadata

