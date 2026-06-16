import pandas as pd
from datetime import datetime
from django.conf import settings
from django.core.management.base import BaseCommand
from coremovieshub.models import TMDBMovie
from django.utils.text import slugify
from django.db import connection
import time
from django.db import OperationalError

class Command(BaseCommand):
    help = "Import TMDB dataset into PostgreSQL"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of records to insert per batch",
        )

    def handle(self, *args, **options):
        csv_path = (
            settings.BASE_DIR
            / "data"
            / "TMDB_movies_final.csv"
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
            
            already_imported = TMDBMovie.objects.count()
            
            self.stdout.write(
                self.style.NOTICE(
                    f"Already imported: {already_imported:,} movies"
                )
            )
            
            chunk_number = 0
            
            for chunk in pd.read_csv(
                csv_path,
                low_memory=False,
                chunksize=batch_size,
            ):
                
                chunk_number += 1
                
                if chunk_number <= already_imported // batch_size:
                    self.stdout.write(
                        f"Skipping Chunk {chunk_number}"
                    )
                    
                    continue

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
                    
                    while True:
                        try:
                            # connection.close()
                            
                            # self.stdout.write(
                            #     f"Connecting to Neon for Chunk {chunk_number}..."
                            # )
                            
                            # connection.connect()
                            
                            TMDBMovie.objects.bulk_create(
                                movies,
                                batch_size=100,
                                ignore_conflicts=True,
                            )
                            
                            database_total = chunk_number * batch_size
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Chunk {chunk_number}: "
                                    f"Database Total: "
                                    f"Approx Total: {database_total:,} movies"
                                )
                            )
                            
                            break
                        
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Chunk {chunk_number}: Connection failed.\n"
                                    f"Reason: {e}\n"
                                    f"Retrying in 10 seconds..."
                                )
                            )
                            connection.close()
                            
                            time.sleep(30)
                            
                            # connection.connect()
                            
                            continue

            final_total = TMDBMovie.objects.count()
            
            self.stdout.write(
                self.style.SUCCESS(
                    "\nImport completed successfully.\n"
                    f"Database Total: {final_total:,} movies"
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Import failed: {e}"
                )
            )
            raise
