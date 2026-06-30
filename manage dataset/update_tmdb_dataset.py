import re
import shutil
from pathlib import Path
from datetime import datetime

import pandas as pd


# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

MASTER_CSV = DATA_DIR / "MoviesHub_metadata.csv"

INCOMING_DIR = DATA_DIR / "incoming"

BACKUP_DIR = DATA_DIR / "backups"

LOG_DIR = DATA_DIR / "logs"

CURRENT_YEAR = datetime.now().year

MIN_YEAR = 2000

MAX_YEAR = CURRENT_YEAR + 2


# ============================================================================
# HELPERS
# ============================================================================

def normalize_title(title):
    """
    Convert titles into searchable normalized versions.
    """

    if pd.isna(title):
        return ""

    title = str(title).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    return title.strip()


def create_directories():
    """
    Create required directories.
    """

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    INCOMING_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def create_backup():
    """
    Backup existing master CSV.
    """

    if not MASTER_CSV.exists():
        return None

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_file = (
        BACKUP_DIR
        /
        f"MoviesHub_metadata_{timestamp}.csv"
    )

    shutil.copy2(
        MASTER_CSV,
        backup_file,
    )

    return backup_file


def get_latest_incoming_csv():
    """
    Get latest CSV from incoming folder.
    """

    csv_files = sorted(
        INCOMING_DIR.glob("*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )

    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found in "
            f"{INCOMING_DIR}"
        )

    return csv_files[0]


def detect_schema(df):
    """
    Detect CSV type.
    """

    columns = set(df.columns)

    if "tmdb_id" in columns:
        return "movieshub"

    if "id" in columns:
        return "tmdb"

    raise ValueError(
        "Unsupported CSV format.\n"
        f"Columns found:\n{df.columns.tolist()}"
    )


def transform_tmdb_schema(df):
    """
    Transform raw TMDB exports.
    """

    df = df.copy()

    df = df.rename(
        columns={
            "id": "tmdb_id",
        }
    )

    required = [
        "tmdb_id",
        "title",
    ]

    for column in required:

        if column not in df.columns:

            raise ValueError(
                f"Missing required "
                f"column: {column}"
            )

    optional_defaults = {

        "overview": "",

        "poster_path": "",

        "backdrop_path": "",

        "genres": "",

        "vote_average": 0,

    }

    for column, default in (
        optional_defaults.items()
    ):

        if column not in df.columns:

            df[column] = default

    if "release_date" not in df.columns:

        df["release_date"] = None

    df["release_date"] = pd.to_datetime(
        df["release_date"],
        errors="coerce",
    )

    df["year"] = (
        df["release_date"]
        .dt.year
    )

    df["title_normalized"] = (
        df["title"]
        .apply(normalize_title)
    )

    df["content_type"] = "movie"

    return df


def transform_movieshub_schema(df):
    """
    Ensure MoviesHub schema.
    """

    df = df.copy()

    if "title_normalized" not in df.columns:

        df["title_normalized"] = (
            df["title"]
            .apply(normalize_title)
        )

    if "year" not in df.columns:

        df["release_date"] = (
            pd.to_datetime(
                df["release_date"],
                errors="coerce",
            )
        )

        df["year"] = (
            df["release_date"]
            .dt.year
        )

    if "content_type" not in df.columns:

        df["content_type"] = "movie"

    return df


def validate_dataset(df):
    """
    Remove bad records.
    """

    df = df.copy()

    initial_count = len(df)

    df = df.dropna(
        subset=[
            "tmdb_id",
            "title",
        ]
    )

    df["year"] = pd.to_numeric(
        df["year"],
        errors="coerce",
    )

    df = df[

        (
            df["year"].isna()
        )

        |

        (
            (
                df["year"]
                >= MIN_YEAR
            )

            &

            (
                df["year"]
                <= MAX_YEAR
            )
        )
    ]

    removed = (
        initial_count
        -
        len(df)
    )

    return df, removed


# ============================================================================
# MAIN
# ============================================================================

def main():

    create_directories()

    print("\n=== MoviesHub TMDB Updater ===\n")

    backup_file = create_backup()

    if backup_file:

        print(
            f"Backup created:\n"
            f"{backup_file}\n"
        )

    print(
        "Loading master dataset..."
    )

    if MASTER_CSV.exists():

        master_df = pd.read_csv(
            MASTER_CSV,
            low_memory=False,
        )

        master_count = len(
            master_df
        )

    else:

        master_df = pd.DataFrame()

        master_count = 0

    print(
        f"Master records: "
        f"{master_count:,}"
    )

    incoming_csv = (
        get_latest_incoming_csv()
    )

    print(
        f"\nIncoming file:\n"
        f"{incoming_csv}"
    )

    incoming_df = pd.read_csv(
        incoming_csv,
        low_memory=False,
    )

    incoming_count = len(
        incoming_df
    )

    print(
        f"Incoming records: "
        f"{incoming_count:,}"
    )

    schema = detect_schema(
        incoming_df
    )

    print(
        f"Detected schema: "
        f"{schema}"
    )

    if schema == "tmdb":

        incoming_df = (
            transform_tmdb_schema(
                incoming_df
            )
        )

    else:

        incoming_df = (
            transform_movieshub_schema(
                incoming_df
            )
        )

    incoming_df, removed = (
        validate_dataset(
            incoming_df
        )
    )

    print(
        f"Invalid rows removed: "
        f"{removed:,}"
    )

    combined = pd.concat(
        [
            master_df,
            incoming_df,
        ],
        ignore_index=True,
    )

    before = len(combined)

    combined = (
        combined
        .drop_duplicates(
            subset="tmdb_id",
            keep="last",
        )
    )

    duplicates = (
        before
        -
        len(combined)
    )

    combined = (
        combined
        .sort_values(
            by=[
                "year",
                "vote_average",
            ],
            ascending=[
                False,
                False,
            ],
        )
    )

    final_columns = [

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

    for column in final_columns:

        if column not in combined.columns:

            combined[column] = ""

    combined = combined[
        final_columns
    ]

    combined.to_csv(
        MASTER_CSV,
        index=False,
    )

    final_count = len(
        combined
    )

    added = (
        final_count
        -
        master_count
    )

    log_file = (
        LOG_DIR
        /
        "update_tmdb.log"
    )

    with open(
        log_file,
        "a",
        encoding="utf-8",
    ) as f:

        f.write(
            f"\n"
            f"{'=' * 50}\n"
        )

        f.write(
            f"{datetime.now()}\n"
        )

        f.write(
            f"Master records: "
            f"{master_count}\n"
        )

        f.write(
            f"Incoming records: "
            f"{incoming_count}\n"
        )

        f.write(
            f"Duplicates removed: "
            f"{duplicates}\n"
        )

        f.write(
            f"Final records: "
            f"{final_count}\n"
        )

        f.write(
            f"Added: "
            f"{added}\n"
        )

    print("\n=== SUMMARY ===")

    print(
        f"Old records: "
        f"{master_count:,}"
    )

    print(
        f"Incoming records: "
        f"{incoming_count:,}"
    )

    print(
        f"Duplicates removed: "
        f"{duplicates:,}"
    )

    print(
        f"Final records: "
        f"{final_count:,}"
    )

    print(
        f"Net added: "
        f"{added:,}"
    )

    print(
        f"\nUpdated master file:\n"
        f"{MASTER_CSV}"
    )

    print(
        f"\nLog file:\n"
        f"{log_file}"
    )


if __name__ == "__main__":

    main()
