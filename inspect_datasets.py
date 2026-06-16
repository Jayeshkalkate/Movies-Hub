import pandas as pd
import re


def normalize(title):
    if pd.isna(title):
        return ""

    title = str(title).lower()

    title = re.sub(r"[^a-z0-9 ]", "", title)

    title = re.sub(r"\s+", " ", title)

    return title.strip()


print("Loading TMDB...")

tmdb = pd.read_csv(
    "data/TMDB_movies_final.csv"
)

tmdb.rename(
    columns={
        "id": "tmdb_id",
    },
    inplace=True,
)

tmdb["title_normalized"] = (
    tmdb["title"]
    .apply(normalize)
)

tmdb["year"] = pd.to_datetime(
    tmdb["release_date"],
    errors="coerce",
).dt.year

tmdb["content_type"] = "movie"

print(
    f"TMDB: {len(tmdb):,}"
)


print("\nLoading Bollywood...")

bollywood = pd.read_csv(
    "data/BollywoodMovieDetail.csv"
)

bollywood = bollywood[
    bollywood["releaseYear"] >= 2010
]

bollywood = bollywood[
    [
        "title",
        "releaseYear",
        "releaseDate",
        "genre",
    ]
]

bollywood.rename(
    columns={
        "releaseYear": "year",
        "releaseDate": "release_date",
        "genre": "genres",
    },
    inplace=True,
)

bollywood["title_normalized"] = (
    bollywood["title"]
    .apply(normalize)
)

bollywood["tmdb_id"] = None

bollywood["overview"] = ""

bollywood["poster_path"] = ""

bollywood["backdrop_path"] = ""

bollywood["vote_average"] = None

bollywood["content_type"] = "movie"

print(
    f"Bollywood: {len(bollywood):,}"
)


print("\nRemoving TMDB duplicates...")

tmdb.drop_duplicates(
    subset=[
        "title_normalized",
        "year",
    ],
    inplace=True,
)

tmdb_keys = set(
    zip(
        tmdb["title_normalized"],
        tmdb["year"],
    )
)


print("Finding Bollywood movies missing from TMDB...")

bollywood = bollywood[
    ~bollywood.apply(
        lambda row: (
            row["title_normalized"],
            row["year"],
        )
        in tmdb_keys,
        axis=1,
    )
]


print(
    f"Bollywood additions: {len(bollywood):,}"
)


final = pd.concat(
    [
        tmdb[
            [
                "tmdb_id",
                "title",
                "title_normalized",
                "overview",
                "poster_path",
                "backdrop_path",
                "genres",
                "release_date",
                "year",
                "vote_average",
                "content_type",
            ]
        ],
        bollywood[
            [
                "tmdb_id",
                "title",
                "title_normalized",
                "overview",
                "poster_path",
                "backdrop_path",
                "genres",
                "release_date",
                "year",
                "vote_average",
                "content_type",
            ]
        ],
    ],
    ignore_index=True,
)


print(
    f"\nFinal MoviesHub Dataset: {len(final):,}"
)

final.to_csv(
    "data/MoviesHub_metadata.csv",
    index=False,
)

print(
    "\nSaved to data/MoviesHub_metadata.csv"
)