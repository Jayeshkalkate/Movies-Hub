import logging
import json
import os
from enum import Enum
from typing import Optional, Set

# Assume ExtractedContent is defined in extractor module
try:
    from extractor import ExtractedContent
except ImportError:
    from dataclasses import dataclass
    from typing import List, Optional

    @dataclass
    class ExtractedContent:
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
# This is a curated list of popular titles.
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
    "the tale of the princess kaguya", "my life as a zucchini",
    # Popular series
    "one punch man", "mob psycho 100", "re:zero", "konosuba", "overlord",
    "fate/stay night", "fate/zero", "monogatari", "bakemonogatari", "nisekoi",
    "toradora", "clannad", "angel beats", "k-on", "haruhi suzumiya",
    "lucky star", "nichijou", "daily lives of high school boys", "school rumble",
    "gurren lagann", "kill la kill", "little witch academia", "promare",
    "redline", "jormungand", "black lagoon", "trigun", "outlaw star",
    "space dandy", "planetes", "mushishi", "natsume's book of friends",
    "barakamon", "silver spoon", "wotakoi", "love is hard for otaku",
    "kaguya-sama: love is war", "love, chunibyo & other delusions",
    "hyouka", "oregairu", "sakurasou", "pet girl of sakurasou",
    "anohana", "the anthem of the heart", "colorful", "the garden of words",
    "your lie in april", "march comes in like a lion", "shirobako",
    "bakuman", "shirokuma cafe", "polar bear cafe", "sayonara zetsubou sensei",
    "sakamoto desu ga", "haven't you heard? i'm sakamoto",
    "the disastrous life of saiki k.", "the devil is a part-timer",
    "no game no life", "problem children are coming from another world, aren't they?",
    "the irregular at magic high school", "mahouka",
    "chivalry of a failed knight", "asterisk war", "infinite stratos",
    "high school dxd", "shinmai maou no testament",
    "testament of sister new devil", "trinity seven",
    "the seven deadly sins", "the rising of the shield hero",
    "that time i got reincarnated as a slime", "saga of tanya the evil",
    "the helpful fox senko-san", "miss kobayashi's dragon maid",
    "dragon maid", "interviews with monster girls",
    "the melancholy of haruhi suzumiya", "haruhi",
    # Newer popular titles
    "blue lock", "solo leveling", "kaiju no.8", "wind breaker", "frieren",
    "dandadan", "chainsaw man", "spy x family", "mashle", "sakamoto days",
    "oshi no ko", "the apothecary diaries", "delicious in dungeon",
    "frieren: beyond journey's end", "solo leveling", "kaiju no 8",
    "wind breaker", "blue lock", "mashle: magic and muscles",
    "dandadan", "chainsaw man", "spy x family", "sakamoto days",
    # Add more as needed
}

# Common keywords that strongly indicate anime (franchise subtitles, etc.)
ANIME_KEYWORDS = {
    "shippuden", "brotherhood", "zero", "gt", "super", "kai", "remake",
    "monogatari", "shippuuden", "z", "next", "generations", "chronicles",
    "re", "rebuild", "alternative", "alternative", "dark", "blood",
    "crimson", "scarlet", "azure", "golden", "silver", "platinum",
    "diamond", "emerald", "ruby", "sapphire", "jade", "onyx",
    "steel", "iron", "titanium", "cobalt", "nickel", "zinc",
    "copper", "brass", "bronze", "tin", "lead", "mercury",
    "platinum", "gold", "silver", "bronze", "iron", "steel",
    "crimson", "scarlet", "azure", "golden", "silver", "platinum",
    "diamond", "emerald", "ruby", "sapphire", "jade", "onyx",
    "steel", "iron", "titanium", "cobalt", "nickel", "zinc",
    "copper", "brass", "bronze", "tin", "lead", "mercury",
    # Common Japanese suffixes
    "chan", "kun", "san", "sama", "senpai", "kouhai",
    "dono", "shishou", "sensei", "kaichou", "fuku",
    # Franchise identifiers
    "naruto", "one piece", "bleach", "dragon ball", "attack on titan",
    "my hero academia", "demon slayer", "jujutsu kaisen", "fullmetal alchemist",
    "hunter x hunter", "death note", "tokyo ghoul", "gintama", "fairy tail",
    "soul eater", "code geass", "steins;gate", "neon genesis evangelion",
    "cowboy bebop", "samurai champloo", "berserk", "sword art online",
    "your name", "weathering with you", "a silent voice",
    "one punch man", "mob psycho 100", "re:zero", "konosuba", "overlord",
    "fate/stay night", "fate/zero", "monogatari", "bakemonogatari", "nisekoi",
    "toradora", "clannad", "angel beats", "k-on", "haruhi suzumiya",
    "lucky star", "nichijou", "daily lives of high school boys", "school rumble",
    "gurren lagann", "kill la kill", "little witch academia", "promare",
    "redline", "jormungand", "black lagoon", "trigun", "outlaw star",
    "space dandy", "planetes", "mushishi", "natsume's book of friends",
    "barakamon", "silver spoon", "wotakoi", "love is hard for otaku",
    "kaguya-sama: love is war", "love, chunibyo & other delusions",
    "hyouka", "oregairu", "sakurasou", "pet girl of sakurasou",
    "anohana", "the anthem of the heart", "colorful", "the garden of words",
    "your lie in april", "march comes in like a lion", "shirobako",
    "bakuman", "shirokuma cafe", "polar bear cafe", "sayonara zetsubou sensei",
    "sakamoto desu ga", "haven't you heard? i'm sakamoto",
    "the disastrous life of saiki k.", "the devil is a part-timer",
    "no game no life", "problem children are coming from another world, aren't they?",
    "the irregular at magic high school", "mahouka",
    "chivalry of a failed knight", "asterisk war", "infinite stratos",
    "high school dxd", "shinmai maou no testament",
    "testament of sister new devil", "trinity seven",
    "the seven deadly sins", "the rising of the shield hero",
    "that time i got reincarnated as a slime", "saga of tanya the evil",
    "the helpful fox senko-san", "miss kobayashi's dragon maid",
    "dragon maid", "interviews with monster girls",
    "the melancholy of haruhi suzumiya", "haruhi",
    # Newer popular titles
    "blue lock", "solo leveling", "kaiju no.8", "wind breaker", "frieren",
    "dandadan", "chainsaw man", "spy x family", "mashle", "sakamoto days",
    "oshi no ko", "the apothecary diaries", "delicious in dungeon",
    "frieren: beyond journey's end", "kaiju no 8",
}


def _load_anime_list() -> Set[str]:
    """Load anime titles from environment variable or use base set."""
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

    Heuristics:
    1. If title is None, return UNKNOWN.
    2. Check if the title (case-insensitive) exists in a curated anime list.
    3. Check if the title contains any anime-specific keywords (e.g., "Shippuden").
    4. If season or episode is present, return TV.
    5. Otherwise, return MOVIE.

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

    # 1. Exact match in anime list
    if title_lower in ANIME_TITLES:
        logger.info(f"Detected anime (exact match): '{extracted.title}'")
        return ContentType.ANIME

    # 2. Check for anime-specific keywords in the title (e.g., "Naruto Shippuden")
    # Split into words and check if any keyword is present as a separate word or part of a word?
    # Better to check substring match for common franchise suffixes.
    for keyword in ANIME_KEYWORDS:
        if keyword in title_lower:
            logger.info(f"Detected anime (keyword '{keyword}'): '{extracted.title}'")
            return ContentType.ANIME

    # 3. TV show detection via season/episode
    if extracted.season is not None or extracted.episode is not None:
        logger.info(f"Detected TV show: '{extracted.title}' (season={extracted.season}, episode={extracted.episode})")
        return ContentType.TV

    # 4. Default to movie
    logger.info(f"Detected movie: '{extracted.title}'")
    return ContentType.MOVIE


# Example usage and simple unit test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    test_cases = [
        ("Naruto", None, None, ContentType.ANIME),
        ("One Piece", None, None, ContentType.ANIME),
        ("Breaking Bad", None, 1, ContentType.TV),  # season present
        ("Money Heist", 1, 1, ContentType.TV),      # season and episode
        ("Pushpa", None, None, ContentType.MOVIE),
        ("Unknown Title", None, None, ContentType.MOVIE),
        (None, None, None, ContentType.UNKNOWN),
        ("Spirited Away", None, None, ContentType.ANIME),
        ("The Matrix", None, None, ContentType.MOVIE),
        ("Blue Lock", None, None, ContentType.ANIME),  # newly added
        ("Solo Leveling", None, None, ContentType.ANIME),
        ("Naruto Shippuden", None, None, ContentType.ANIME),  # keyword
        ("Fullmetal Alchemist Brotherhood", None, None, ContentType.ANIME),
        ("Attack on Titan", None, None, ContentType.ANIME),
    ]

    for title, season, episode, expected in test_cases:
        extracted = ExtractedContent(title=title, season=season, episode=episode)
        result = detect(extracted)
        status = "PASS" if result == expected else "FAIL"
        print(f"{status}: title='{title}', season={season}, episode={episode} -> {result} (expected {expected})")