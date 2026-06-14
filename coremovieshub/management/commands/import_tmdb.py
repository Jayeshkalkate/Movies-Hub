import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand

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
            for chunk in pd.read_csv(
                csv_path,
                low_memory=False,
                chunksize=batch_size,
            ):

                movies = []

                for _, row in chunk.iterrows():

                    title = row.get("title")

                    if pd.isna(title):
                        continue

                    movies.append(
                        TMDBMovie(
                            tmdb_id=(
                                int(row["id"])
                                if pd.notna(row.get("id"))
                                else None
                            ),

                            title=str(title).strip(),

                            overview=(
                                row.get("overview", "")
                                if pd.notna(
                                    row.get("overview")
                                )
                                else ""
                            ),

                            poster_path=(
                                row.get("poster_path", "")
                                if pd.notna(
                                    row.get("poster_path")
                                )
                                else ""
                            ),

                            backdrop_path=(
                                row.get("backdrop_path", "")
                                if pd.notna(
                                    row.get("backdrop_path")
                                )
                                else ""
                            ),

                            release_date=(
                                row.get("release_date")
                                if pd.notna(
                                    row.get("release_date")
                                )
                                else None
                            ),

                            vote_average=(
                                float(
                                    row.get(
                                        "vote_average"
                                    )
                                )
                                if pd.notna(
                                    row.get(
                                        "vote_average"
                                    )
                                )
                                else None
                            ),
                        )
                    )

                TMDBMovie.objects.bulk_create(
                    movies,
                    batch_size=batch_size,
                    ignore_conflicts=True,
                )

                total_imported += len(movies)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Imported: {total_imported:,} movies"
                    )
                )

            self.stdout.write(
                self.style.SUCCESS(
                    "\n"
                    f"Import completed successfully.\n"
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