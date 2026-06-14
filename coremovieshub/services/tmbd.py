import requests
from django.conf import settings


def search_movie(title):

    url = (
        "https://api.themoviedb.org/3/search/movie"
    )

    response = requests.get(
        url,
        params={
            "api_key": settings.TMDB_API_KEY,
            "query": title,
        }
    )

    data = response.json()

    results = data.get("results", [])

    if not results:
        return None

    movie = results[0]

    return {
        "poster":
            f"https://image.tmdb.org/t/p/w500"
            f"{movie.get('poster_path')}"
            if movie.get("poster_path")
            else "",

        "banner":
            f"https://image.tmdb.org/t/p/original"
            f"{movie.get('backdrop_path')}"
            if movie.get("backdrop_path")
            else "",

        "overview":
            movie.get("overview", ""),

        "rating":
            movie.get("vote_average"),

        "release_date":
            movie.get("release_date"),
    }