import pandas as pd
import re
from pathlib import Path


# ==========================
# Configuration
# ==========================
BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

MOVIESHUB_FILE = r"C:\Projects\movieshub\data\MoviesHub_metadata.csv"

KAGGLE_FILE = (
    r"C:\Projects\movieshub\data\incoming"
    r"\MoviesHub_metadata_2000_2026.csv"
)

OUTPUT_FILE = (
    r"C:\Projects\movieshub\data"
    r"\MoviesHub_metadata_merged.csv"
)


# ==========================
# Title normalization
# ==========================
def normalize_title(title):
    if pd.isna(title):
        return ""

    title = str(title).lower()

    # Remove punctuation
    title = re.sub(r"[^\w\s]", "", title)

    # Remove extra spaces
    title = re.sub(r"\s+", " ", title).strip()

    return title


# ==========================
# Load MoviesHub dataset
# ==========================
print("Loading MoviesHub dataset...")

movieshub_df = pd.read_csv(
    MOVIESHUB_FILE,
    low_memory=False
)

print(f"MoviesHub records: {len(movieshub_df):,}")


# ==========================
# Load Kaggle dataset
# ==========================
print("Loading Kaggle dataset...")

kaggle_df = pd.read_csv(
    KAGGLE_FILE,
    low_memory=False
)

print(f"Kaggle records: {len(kaggle_df):,}")


# ==========================
# Keep only 2000–2026
# ==========================
if "year" in kaggle_df.columns:
    kaggle_df["year"] = pd.to_numeric(
        kaggle_df["year"],
        errors="coerce"
    )

    kaggle_df = kaggle_df[
        kaggle_df["year"].between(2000, 2026)
    ]

print(f"Kaggle records (2000–2026): {len(kaggle_df):,}")


# ==========================
# MoviesHub required columns
# ==========================
required_columns = [
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


# Add missing columns
for col in required_columns:
    if col not in movieshub_df.columns:
        movieshub_df[col] = None

    if col not in kaggle_df.columns:
        kaggle_df[col] = None


# Keep only required columns
movieshub_df = movieshub_df[required_columns]
kaggle_df = kaggle_df[required_columns]


# ==========================
# Normalize titles
# ==========================
print("Normalizing titles...")

movieshub_df["title_normalized"] = (
    movieshub_df["title"]
    .fillna("")
    .apply(normalize_title)
)

kaggle_df["title_normalized"] = (
    kaggle_df["title"]
    .fillna("")
    .apply(normalize_title)
)


# ==========================
# Merge datasets
# ==========================
print("Merging datasets...")

merged_df = pd.concat(
    [movieshub_df, kaggle_df],
    ignore_index=True
)

print(f"Before duplicate removal: {len(merged_df):,}")


# ==========================
# Remove duplicates
# ==========================
if "tmdb_id" in merged_df.columns:
    merged_df = merged_df.drop_duplicates(
        subset=["tmdb_id"],
        keep="first"
    )

merged_df = merged_df.drop_duplicates(
    subset=["title_normalized", "year"],
    keep="first"
)

print(f"After duplicate removal: {len(merged_df):,}")


# ==========================
# Sort by year and title
# ==========================
merged_df = merged_df.sort_values(
    by=["year", "title"],
    ascending=[False, True]
)


# ==========================
# Save merged dataset
# ==========================
merged_df.to_csv(
    OUTPUT_FILE,
    index=False
)

print("\nMerge completed successfully!")
print(f"Final records: {len(merged_df):,}")
print(f"Saved to: {OUTPUT_FILE}")