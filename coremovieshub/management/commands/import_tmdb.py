import pandas as pd
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from coremovieshub.models import TMDBMovie


class Command(BaseCommand):
    help = "Import TMDB dataset into PostgreSQL"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=5000,
            help="Number of records to insert per batch",
        )

    def handle(self, *args, **options):
        csv_path = (
            settings.BASE_DIR
            / "data"
            / "TMDB_movie_dataset_v11.csv"
        )

        batch_size = options["batch_size"]

        self.stdout.write(
            self.style.NOTICE(
                f"Importing TMDB dataset from:\n{csv_path}"
            )
        )

        if not csv_path.exists():
            self.stdout.write(
                self.style.ERROR(
                    f"CSV file not found:\n{csv_path}"
                )
            )
            return

        total_imported = 0

        try:
            for chunk_number, chunk in enumerate(
                pd.read_csv(
                    csv_path,
                    low_memory=False,
                    chunksize=batch_size,
                ),
                start=1,
            ):

                movies = []

                for row in chunk.itertuples(index=False):

                    try:
                        title = getattr(row, "title", None)

                        if (
                            pd.isna(title)
                            or not str(title).strip()
                        ):
                            continue

                        title = str(title).strip()

                        tmdb_id = getattr(row, "id", None)

                        overview = getattr(
                            row,
                            "overview",
                            "",
                        )

                        poster_path = getattr(
                            row,
                            "poster_path",
                            "",
                        )

                        backdrop_path = getattr(
                            row,
                            "backdrop_path",
                            "",
                        )

                        release_date = None

                        release_date_str = getattr(
                            row,
                            "release_date",
                            None,
                        )

                        if (
                            pd.notna(release_date_str)
                            and str(
                                release_date_str
                            ).strip()
                        ):
                            try:
                                release_date = (
                                    datetime.strptime(
                                        str(
                                            release_date_str
                                        ),
                                        "%Y-%m-%d",
                                    ).date()
                                )
                            except ValueError:
                                release_date = None

                        vote_average = getattr(
                            row,
                            "vote_average",
                            None,
                        )

                        tmdb_id = (
                            int(tmdb_id)
                            if pd.notna(tmdb_id)
                            else None
                        )

                        title_normalized = (
                            slugify(title)
                        )

                        if tmdb_id:
                            title_normalized = (
                                f"{title_normalized}-{tmdb_id}"
                            )

                        movies.append(
                            TMDBMovie(
                                tmdb_id=tmdb_id,

                                title=title,

                                title_normalized=(
                                    title_normalized
                                ),

                                overview=(
                                    str(overview)
                                    if pd.notna(
                                        overview
                                    )
                                    else ""
                                ),

                                poster_path=(
                                    str(
                                        poster_path
                                    )
                                    if pd.notna(
                                        poster_path
                                    )
                                    else ""
                                ),

                                backdrop_path=(
                                    str(
                                        backdrop_path
                                    )
                                    if pd.notna(
                                        backdrop_path
                                    )
                                    else ""
                                ),

                                release_date=release_date,

                                vote_average=(
                                    float(
                                        vote_average
                                    )
                                    if pd.notna(
                                        vote_average
                                    )
                                    else None
                                ),
                            )
                        )

                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Skipping record: {e}"
                            )
                        )
                        continue

                if movies:
                    with transaction.atomic():
                        TMDBMovie.objects.bulk_create(
                            movies,
                            batch_size=batch_size,
                            ignore_conflicts=True,
                        )

                    total_imported += len(
                        movies
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Chunk {chunk_number}: "
                        f"Imported "
                        f"{total_imported:,} movies"
                    )
                )

            self.stdout.write(
                self.style.SUCCESS(
                    "\nImport completed successfully.\n"
                    f"Total imported: "
                    f"{total_imported:,} movies"
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Import failed: {e}"
                )
            )
            raise