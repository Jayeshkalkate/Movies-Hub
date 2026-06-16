
import pandas as pd

print("Reading CSV...")

df = pd.read_csv(
    "data/Data_for_repository.csv",
    low_memory=False,
)

print(f"Original movies: {len(df):,}")

df["release_date"] = pd.to_datetime(
    df["release_date"],
    errors="coerce",
)

filtered = df[
    (df["release_date"].dt.year >= 2000)
    &
    (df["release_date"].dt.year <= 2026)
]

print(f"Filtered movies: {len(filtered):,}")

filtered.to_csv(
    "data/TMDB_movies_2000_2026.csv",
    index=False,
)

print("Done!")
print(
    "Saved to data/p1.csv"
)