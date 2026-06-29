import requests
from difflib import SequenceMatcher
from django.conf import settings


def search_movie(title, year=None):
    """
    Search TMDb for a movie by title, optionally filtering by year.
    Returns the best matching movie based on title similarity, year match, and popularity.
    """
    url = "https://api.themoviedb.org/3/search/movie"

    params = {
        "api_key": settings.TMDB_API_KEY,
        "query": title,
    }
    if year:
        params["year"] = year  # TMDb supports year param for movie search

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        # Log error if needed
        return None

    results = data.get("results", [])
    if not results:
        return None

    # Score each result
    scored = []
    for movie in results:
        score = 0.0

        # 1. Title similarity (compare with original title and title)
        movie_title = movie.get("title", "")
        original_title = movie.get("original_title", "")
        # Use the better match between title and original_title
        best_title = movie_title if movie_title else original_title
        if best_title:
            # Case-insensitive partial matching
            sim = SequenceMatcher(None, title.lower(), best_title.lower()).ratio()
            # Give full match a boost
            if sim >= 0.9:
                score += 10.0
            else:
                score += sim * 5.0  # scale down

        # 2. Year match (if provided)
        if year:
            release_date = movie.get("release_date")
            if release_date and release_date.startswith(str(year)):
                score += 5.0

        # 3. Popularity / vote count
        popularity = movie.get("popularity", 0)
        vote_count = movie.get("vote_count", 0)
        # Normalize popularity (max ~1000, but we can cap)
        pop_score = min(popularity / 100, 1.0) * 2.0  # max 2 points
        vote_score = min(vote_count / 1000, 1.0) * 1.0  # max 1 point
        score += pop_score + vote_score

        # Store score with movie
        scored.append((score, movie))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Pick the best
    best_movie = scored[0][1]

    return {
        "poster": (
            f"https://image.tmdb.org/t/p/w500{best_movie.get('poster_path')}"
            if best_movie.get("poster_path")
            else ""
        ),
        "banner": (
            f"https://image.tmdb.org/t/p/original{best_movie.get('backdrop_path')}"
            if best_movie.get("backdrop_path")
            else ""
        ),
        "overview": best_movie.get("overview", ""),
        "rating": best_movie.get("vote_average"),
        "release_date": best_movie.get("release_date"),
    }
    
