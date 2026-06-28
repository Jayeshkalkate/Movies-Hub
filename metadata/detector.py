"""
Content type detector for movies, TV shows, and anime.

This module determines whether a given piece of content (extracted from a filename
or caption) is a movie, a TV series, or anime. It uses a combination of heuristics:

1. Presence of season/episode numbers → TV series (highest priority)
2. Title matches a curated list of anime titles or contains anime keywords → Anime
3. Fallback → Movie

The anime list can be extended via the `ANIME_LIST_PATH` environment variable
(pointing to a JSON file containing a list of anime titles).

Usage:
    from detector import detect, ContentType
    from extractor import ExtractedContent

    extracted = ExtractedContent(title="Naruto Shippuden", season=1, episode=5)
    content_type = detect(extracted)  # ContentType.ANIME
"""

import logging
import json
import os
from enum import Enum
from typing import Optional, Set, List

# Try to import ExtractedContent from the extractor module
try:
    from extractor import ExtractedContent
except ImportError:
    from dataclasses import dataclass
    from typing import Optional, List

    @dataclass
    class ExtractedContent:
        """Minimal placeholder for ExtractedContent if extractor is not available."""
        title: Optional[str] = None
        year: Optional[int] = None
        season: Optional[int] = None
        episode: Optional[int] = None
        quality: Optional[str] = None
        languages: Optional[List[str]] = None


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ContentType(Enum):
    """Enumeration of possible content types."""
    MOVIE = "movie"
    TV = "tv"
    ANIME = "anime"
    UNKNOWN = "unknown"


# ------------------- Anime detection data -------------------

# Core set of known anime titles (lowercase, deduplicated)
# This is a curated list of popular titles covering various genres and eras.
# To extend, set the environment variable ANIME_LIST_PATH to a JSON file
# containing a list of strings, or directly modify this set.
BASE_ANIME_TITLES = {
    # Classic shonen
    "naruto", "one piece", "bleach", "dragon ball", "dragon ball z", "dragon ball super",
    "attack on titan", "my hero academia", "demon slayer", "jujutsu kaisen",
    "fullmetal alchemist", "fullmetal alchemist brotherhood", "hunter x hunter",
    "death note", "tokyo ghoul", "gintama", "fairy tail", "soul eater",
    "code geass", "steins;gate", "neon genesis evangelion",
    # Studio Ghibli and movies
    "spirited away", "princess mononoke", "my neighbor totoro", "howl's moving castle",
    "grave of the fireflies", "akira", "ghost in the shell", "cowboy bebop",
    "samurai champloo", "berserk", "sword art online", "your name",
    "weathering with you", "a silent voice", "i want to eat your pancreas",
    "the girl who leapt through time", "5 centimeters per second", "garden of words",
    "millennium actress", "paprika", "perfect blue", "summer wars", "wolf children",
    "the boy and the beast", "when marnie was there", "only yesterday",
    "pom poko", "the cat returns", "whisper of the heart", "from up on poppy hill",
    "the tale of the princess kaguya",
    # Popular series
    "one punch man", "mob psycho 100", "re:zero", "konosuba", "overlord",
    "fate/stay night", "fate/zero", "monogatari", "bakemonogatari", "nisekoi",
    "toradora", "clannad", "angel beats", "k-on", "haruhi suzumiya",
    "lucky star", "nichijou", "gurren lagann", "kill la kill",
    "little witch academia", "promare", "redline", "jormungand",
    "black lagoon", "trigun", "outlaw star", "space dandy", "planetes",
    "mushishi", "natsume's book of friends", "barakamon", "silver spoon",
    "wotakoi", "kaguya-sama: love is war", "hyouka", "oregairu",
    "sakurasou", "anohana", "the anthem of the heart", "colorful",
    "your lie in april", "march comes in like a lion", "shirobako",
    "bakuman", "shirokuma cafe", "sayonara zetsubou sensei",
    "the disastrous life of saiki k.", "the devil is a part-timer",
    "no game no life", "the irregular at magic high school", "mahouka",
    "chivalry of a failed knight", "asterisk war", "infinite stratos",
    "high school dxd", "shinmai maou no testament", "trinity seven",
    "the seven deadly sins", "the rising of the shield hero",
    "that time i got reincarnated as a slime", "saga of tanya the evil",
    "miss kobayashi's dragon maid", "dragon maid",
    "the melancholy of haruhi suzumiya", "haruhi",
    # Newer popular titles
    "blue lock", "solo leveling", "kaiju no.8", "wind breaker", "frieren",
    "dandadan", "chainsaw man", "spy x family", "mashle", "sakamoto days",
    "oshi no ko", "the apothecary diaries", "delicious in dungeon",
    "frieren: beyond journey's end", "kaiju no 8", "sakamoto days",
    # Additional notable titles
    "death parade", "psycho-pass", "terror in resonance", "zankyou no terror",
    "ergo proxy", "serial experiments lain", "paranoia agent", "paprika",
    "texhnolyze", "haibane renmei", "kino's journey", "girls' last tour",
    "made in abyss", "land of the lustrous", "houseki no kuni",
    "ancient magus' bride", "the case study of vanitas", "vanitas no carte",
    "to your eternity", "fumetsu no anata e", "vivy: fluorite eye's song",
    "odd taxi", "ranking of kings", "ousama ranking", "heike monogatari",
    "the heike story", "sonny boy", "wonder egg priority",
}

# Common keywords that strongly indicate anime (franchise subtitles, etc.)
# These are used as a secondary check, but we avoid overly generic terms.
ANIME_KEYWORDS = {
    # Franchise subtitles
    "shippuden", "brotherhood", "gt", "super", "kai", "remake",
    "chronicles", "rebuild", "alternative", "crimson", "scarlet",
    "azure", "golden", "silver", "platinum", "diamond", "emerald",
    "ruby", "sapphire", "jade", "onyx", "steel", "iron", "titanium",
    "cobalt", "nickel", "zinc", "copper", "brass", "bronze", "tin",
    "lead", "mercury", "platinum", "gold", "silver", "bronze",
    # Common Japanese honorifics/titles (indicate anime origin)
    "chan", "kun", "san", "sama", "senpai", "kouhai", "dono",
    "shishou", "sensei", "kaichou", "fuku",
}


def _load_anime_list() -> Set[str]:
    """
    Load anime titles from environment variable or use base set.

    The environment variable ANIME_LIST_PATH should point to a JSON file
    containing a list of strings. Each string is a title (case-insensitive).

    Returns:
        Set[str]: A set of lowercase anime titles.
    """
    titles = set(BASE_ANIME_TITLES)
    custom_path = os.environ.get("ANIME_LIST_PATH")
    if custom_path and os.path.exists(custom_path):
        try:
            with open(custom_path, "r", encoding="utf-8") as f:
                custom = json.load(f)
                if isinstance(custom, list):
                    titles.update(t.lower() for t in custom)
                    logger.info(f"Loaded {len(custom)} custom anime titles from {custom_path}")
                else:
                    logger.warning(f"Custom anime list at {custom_path} is not a list, ignoring.")
        except Exception as e:
            logger.error(f"Failed to load anime list from {custom_path}: {e}")
    return titles


ANIME_TITLES = _load_anime_list()


def detect(extracted: ExtractedContent) -> ContentType:
    """
    Determine the content type (movie, TV show, anime, or unknown)
    based on the extracted metadata.

    Heuristics (in order of priority):
    1. If title is None → UNKNOWN.
    2. If season or episode is present → TV (even if anime, we classify as TV).
       This ensures that any series with episode numbering is not misclassified as movie.
    3. If the title (case-insensitive) exists in a curated anime list → ANIME.
    4. If the title contains anime-specific keywords → ANIME.
    5. Otherwise → MOVIE.

    Args:
        extracted: An ExtractedContent instance.

    Returns:
        ContentType enum value.
    """
    if extracted.title is None:
        logger.debug("Title is None, cannot classify.")
        return ContentType.UNKNOWN

    title_lower = extracted.title.lower().strip()
    logger.debug(f"Classifying title: '{extracted.title}' (lower: '{title_lower}')")

    # Priority 1: TV detection via season/episode
    if extracted.season is not None or extracted.episode is not None:
        logger.info(f"Detected TV show (season/episode present): '{extracted.title}' "
                    f"(season={extracted.season}, episode={extracted.episode})")
        return ContentType.TV

    # Priority 2: Exact match in anime list
    if title_lower in ANIME_TITLES:
        logger.info(f"Detected anime (exact match): '{extracted.title}'")
        return ContentType.ANIME

    # Priority 3: Anime-specific keyword match (substring)
    for keyword in ANIME_KEYWORDS:
        if keyword in title_lower:
            logger.info(f"Detected anime (keyword '{keyword}'): '{extracted.title}'")
            return ContentType.ANIME

    # Priority 4: Fallback to movie
    logger.info(f"Detected movie (fallback): '{extracted.title}'")
    return ContentType.MOVIE


# Example usage and simple unit test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    test_cases = [
        # (title, season, episode, expected)
        ("Naruto", None, None, ContentType.ANIME),
        ("One Piece", None, None, ContentType.ANIME),
        ("Breaking Bad", None, 1, ContentType.TV),       # episode present → TV
        ("Money Heist", 1, 1, ContentType.TV),           # season and episode → TV
        ("Pushpa", None, None, ContentType.MOVIE),
        ("Unknown Title", None, None, ContentType.MOVIE),
        (None, None, None, ContentType.UNKNOWN),
        ("Spirited Away", None, None, ContentType.ANIME),
        ("The Matrix", None, None, ContentType.MOVIE),
        ("Blue Lock", None, None, ContentType.ANIME),
        ("Solo Leveling", None, None, ContentType.ANIME),
        ("Naruto Shippuden", None, None, ContentType.ANIME),  # keyword
        ("Fullmetal Alchemist Brotherhood", None, None, ContentType.ANIME),
        ("Attack on Titan", None, None, ContentType.ANIME),
        # This should be TV, not anime, because season exists
        ("Suzume", 1, None, ContentType.TV),  # even if it's a movie, season makes it TV
        ("Weak Hero Class 1", None, None, ContentType.MOVIE),  # not in anime list, no season
    ]

    for title, season, episode, expected in test_cases:
        extracted = ExtractedContent(title=title, season=season, episode=episode)
        result = detect(extracted)
        status = "PASS" if result == expected else "FAIL"
        print(f"{status}: title='{title}', season={season}, episode={episode} -> {result} (expected {expected})")