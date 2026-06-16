import re

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from coremovieshub.models import (
    TelegramMovie,
    TMDBMovie,
)


class Command(BaseCommand):
    help = "Sync TelegramMovie metadata from TMDB dataset"

    def clean_title(self, title):
        """
        Remove release-group and quality junk.
        """

        title = re.sub(
            r'\b(720p|1080p|2160p|480p)\b',
            '',
            title,
            flags=re.IGNORECASE,
        )

        title = re.sub(
            r'\b(BluRay|WEBRip|WEB-DL|HDRip|HEVC|x264|x265|AAC|DDP?|ESub|NF)\b',
            '',
            title,
            flags=re.IGNORECASE,
        )

        title = re.sub(
            r'\b(Hindi|English|Dual Audio|Multi Audio)\b',
            '',
            title,
            flags=re.IGNORECASE,
        )

        title = re.sub(
            r'\([^)]*\)',
            '',
            title,
        )

        title = re.sub(
            r'\s+',
            ' ',
            title,
        )
        
        title = title.replace(
            "Spider Man",
            "Spider-Man"
        )
        
        title = title.replace(
            "Top Gun Maverick",
            "Top Gun: Maverick"
        )
        
        title = title.replace(
            "A Silent Voice 2016",
            "A Silent Voice"
        )
        
        title = title.replace(
            "Moana 2016",
            "Moana"
        )
        
        title = re.sub(
            r'\bSeason\s+\d+\b',
            '',
            title,
            flags=re.IGNORECASE
        )
        
        title = re.sub(
            r'\bPart\s+\d+\b',
            '',
            title,
            flags=re.IGNORECASE
        )
        
        title = re.sub(
            r'\bChapter\s+\d+\b',
            '',
            title,
            flags=re.IGNORECASE
        )
        
        title = re.sub(
            r'\bI\b',
            '',
            title,
        )
        
        return title.strip()

    def handle(self, *args, **options):

        updated = 0
        not_found = 0

        movies = TelegramMovie.objects.all()

        total = movies.count()

        self.stdout.write(
            f"Processing {total} movies..."
        )

        for movie in movies:

            original_title = movie.title

            import re
            year_match = re.search(
                r'(19|20)\d{2}',
                original_title
            )
            
            if year_match and not movie.year:
                movie.year = int(year_match.group())
                
            cleaned_title = self.clean_title(original_title)

            tmdb = None

            # Exact match
            queryset = TMDBMovie.objects.filter(
                title__iexact=cleaned_title
            )

            if movie.year:
                queryset = queryset.filter(
                    release_date__year=movie.year
                )

            tmdb = queryset.first()

            # Partial match
            if not tmdb:

                queryset = TMDBMovie.objects.filter(
                    title__icontains=cleaned_title
                )

                if movie.year:
                    queryset = queryset.filter(
                        release_date__year=movie.year
                    )

                tmdb = queryset.order_by(
                    "-vote_average"
                ).first()

            if not tmdb:

                not_found += 1

                self.stdout.write(
                    self.style.WARNING(
                        f"NOT FOUND: {movie.title}"
                    )
                )

                continue

            changed = False

            movie.tmdb_id = tmdb.tmdb_id

            if not movie.overview:
                movie.overview = tmdb.overview
                changed = True

            if not movie.poster:
                movie.poster = (
                    "https://image.tmdb.org/t/p/w500"
                    f"{tmdb.poster_path}"
                )
                changed = True

            if not movie.year and tmdb.release_date:
                movie.year = tmdb.release_date.year
                changed = True

            if not movie.rating:
                movie.rating = tmdb.vote_average
                changed = True

            if not movie.tags:
                movie.tags = tmdb.genres
                changed = True

            if (
                not movie.duration
                and getattr(tmdb, "runtime", None)
            ):
                movie.duration = (
                    f"{tmdb.runtime} min"
                )
                changed = True

            if (
                not movie.season_count
                and getattr(
                    tmdb,
                    "number_of_seasons",
                    None,
                )
            ):
                movie.season_count = (
                    tmdb.number_of_seasons
                )
                changed = True

            if (
                not movie.episode_count
                and getattr(
                    tmdb,
                    "number_of_episodes",
                    None,
                )
            ):
                movie.episode_count = (
                    tmdb.number_of_episodes
                )
                changed = True

            if not movie.status:

                tmdb_status = (
                    getattr(
                        tmdb,
                        "status",
                        "",
                    )
                    .lower()
                )

                if tmdb_status == "ended":
                    movie.status = "completed"

                elif tmdb_status in [
                    "returning series",
                    "ongoing",
                ]:
                    movie.status = "ongoing"

                elif tmdb_status in [
                    "planned",
                    "in production",
                ]:
                    movie.status = "upcoming"

                changed = True

            if changed:

                movie.save()

                updated += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"UPDATED: {movie.title}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCompleted!\n"
                f"Updated: {updated}\n"
                f"Not Found: {not_found}"
            )
        )