from coremovieshub.models import TMDBMovie
import re

def normalize_title(title):
    if not title:
        return ""

    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title

def find_by_title(title, content_type=None, year=None):
    normalized = normalize_title(title)

    movie = TMDBMovie.objects.filter(
        title_normalized=normalized
    ).first()

    if not movie:
        return None

    return {
        "external_id": movie.tmdb_id,
        "source": "tmdb",
        "title": movie.title,
        "overview": movie.overview,
        "poster": movie.poster_path,
        "backdrop": movie.backdrop_path,
        "release_date": movie.release_date,
        "rating": movie.vote_average,
    }

def save_metadata(data):
    normalized = normalize_title(data["title"])

    movie, created = TMDBMovie.objects.update_or_create(
        tmdb_id=data["external_id"],
        defaults={
            "title": data["title"],
            "title_normalized": normalized,
            "poster_path": data.get("poster", ""),
            "backdrop_path": data.get("backdrop", ""),
            "overview": data.get("overview", ""),
            "genres": ",".join(data.get("genres", []))
            if isinstance(data.get("genres"), list)
            else data.get("genres", ""),
            "release_date": data.get("release_date"),
            "vote_average": data.get("rating"),
        }
    )

    return movie

