import pandas as pd
from django.conf import settings


DATA_PATH = (
    settings.BASE_DIR
    / "data"
    / "TMDB_movie_dataset_v11.csv"
)


# Lazy-loaded dataframe
movies_df = None


def get_movies_df():
    """
    Load the TMDB dataset only when it is first needed.
    Subsequent calls reuse the already loaded dataframe.
    """
    global movies_df

    if movies_df is None:
        print("Loading TMDB dataset...")

        movies_df = pd.read_csv(
            DATA_PATH,
            low_memory=False,
        )

        movies_df["title"] = (
            movies_df["title"]
            .astype(str)
            .str.lower()
        )

        print(
            f"TMDB dataset loaded successfully "
            f"({len(movies_df)} movies)"
        )

    return movies_df


def search_movie_metadata(title):
    """
    Search TMDB metadata by movie title.
    Returns a dictionary of metadata or None.
    """

    if not title:
        return None

    title = title.lower().strip()

    df = get_movies_df()
    
    exact = df[
        df["title"] == title
        ]
    
    if not exact.empty:
        movie = exact.iloc[0]
        
        return {
            "poster": (
                f"https://image.tmdb.org/t/p/w500"
                f"{movie['poster_path']}"
                if pd.notna(movie["poster_path"])
                else ""
                ),
            
            "banner": (
                f"https://image.tmdb.org/t/p/original"
                f"{movie['backdrop_path']}"
                if pd.notna(movie["backdrop_path"])
                else ""
                ),
            
            "overview": (
                movie["overview"]
                if pd.notna(movie["overview"])
                else ""
                ),
            
            "rating": (
                float(movie["vote_average"])
                if pd.notna(movie["vote_average"])
                else None
                ),

            "release_date": (
                movie["release_date"]
                if pd.notna(movie["release_date"])
                else None
                ),
            
            }
        
    matches = df[
        df["title"].str.contains(
            title,
            na=False
            )
        ]

    if matches.empty:
        return None

    movie = matches.iloc[0]

    return {
        "poster": (
            f"https://image.tmdb.org/t/p/w500"
            f"{movie['poster_path']}"
            if pd.notna(movie["poster_path"])
            else ""
        ),

        "banner": (
            f"https://image.tmdb.org/t/p/original"
            f"{movie['backdrop_path']}"
            if pd.notna(movie["backdrop_path"])
            else ""
        ),

        "overview": (
            movie.get("overview", "")
            if pd.notna(movie.get("overview"))
            else ""
        ),

        "rating": (
            float(movie.get("vote_average"))
            if pd.notna(movie.get("vote_average"))
            else None
        ),

        "release_date": (
            movie.get("release_date")
            if pd.notna(movie.get("release_date"))
            else None
        ),
    }