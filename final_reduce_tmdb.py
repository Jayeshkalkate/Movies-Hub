import pandas as pd

input_csv = r"C:\Projects\movieshub\data\TMDB_movies_2000_2026.csv"
output_csv = r"C:\Projects\movieshub\data\TMDB_movie_final.csv"

print("Reading CSV...")

df = pd.read_csv(input_csv)

print(f"Current movies: {len(df):,}")

df = df[
    (df["vote_average"] >= 5.0)
    &
    (df["poster_path"].notna())
    &
    (df["poster_path"] != "")
]

print(f"Final movies: {len(df):,}")

df.to_csv(output_csv, index=False)

print("Final CSV saved successfully!")