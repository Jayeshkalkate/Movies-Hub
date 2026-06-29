from django.core.management.base import BaseCommand

from coremovieshub.models import TelegramMovie
        
from coremovieshub.services.movie_metadata import (
    search_movie_metadata,
)

from coremovieshub.utils.movie_parser import (
    extract_title,
    extract_year,
)

class Command(BaseCommand):

    help = "Enrich Telegram movies with TMDB metadata"

    def handle(self, *args, **kwargs):
        
        movies = TelegramMovie.objects.filter(
            tmdb_id__isnull=True,
            content_type="movie",
        )

        total = movies.count()

        self.stdout.write(
            f"{total} movies to enrich"
        )

        for movie in movies:

            clean_title = extract_title(movie.title)
            
            year = (
                movie.year
                or extract_year(movie.title)
            )
            
            metadata = search_movie_metadata(
                title=clean_title,
                year=year,
            )

            if not metadata:
                continue

            # ---- Preserve existing Telegram data ----
            # Only set fields that are currently empty
            if not movie.poster:
                movie.poster = metadata.get("poster")
            
            if not movie.banner:
                movie.banner = metadata.get("banner")
            
            if not movie.overview:
                movie.overview = metadata.get("overview")
            
            if not movie.rating:
                movie.rating = metadata.get("rating")
            
            if not movie.release_date:
                movie.release_date = metadata.get("release_date")
            
            if not movie.tmdb_id:
                movie.tmdb_id = metadata.get("tmdb_id")
            
            # **** CRITICAL: Do NOT overwrite the original title ****
            if not movie.title:
                movie.title = clean_title

            movie.save()

            self.stdout.write(
                f"Updated: {movie.title}"
            )
            
