import pandas as pd

input_csv = r"C:\Projects\movieshub\data\TMDB_movies_2000_2026.csv"
output_csv = r"C:\Projects\movieshub\data\TMDB_movie_filtered.csv"

columns = [
    "id",
    "title",
    "backdrop_path",
    "poster_path",
    "overview",
    "genres",
    "release_date",
    "vote_average",
]

pd.read_csv(
    input_csv,
    usecols=columns,
).to_csv(
    output_csv,
    index=False,
)

print("Reduced CSV created successfully!")