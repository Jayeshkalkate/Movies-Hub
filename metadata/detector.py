"""
Content type detector for movies, TV shows, and anime.

Enhanced with:
- Subtype detection (OVA, ONA, Movie, Special, Final Season, Part 2)
- Fallback season/episode parsing from title (E120, S02E08, etc.)
- Language detection from text
- Quality detection (optional)
- Robust anime title matching from built-in list and external JSON file
"""

import logging
import json
import os
import re
from enum import Enum
from typing import Optional, Set, List, Tuple
from dataclasses import dataclass, field

# Configure logging (will be overridden by caller if needed)
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ContentType(Enum):
    MOVIE = "movie"
    TV = "tv"
    ANIME = "anime"
    UNKNOWN = "unknown"


# ---------- ExtractedContent (if not imported) ----------
try:
    from metadata.extractor2 import ExtractedContent
except ImportError:
    @dataclass
    class ExtractedContent:
        title: Optional[str] = None
        year: Optional[int] = None
        season: Optional[int] = None
        episode: Optional[int] = None
        quality: Optional[str] = None
        languages: Optional[List[str]] = None
        subtype: Optional[str] = None          # OVA, ONA, Movie, etc.


# ---------- Anime data ----------
# Built-in fallback anime titles (a reasonable list of well-known series)
DEFAULT_ANIME_TITLES = {
    "naruto", "naruto shippuden", "boruto", "one piece", "bleach",
    "attack on titan", "shingeki no kyojin", "demon slayer", "kimetsu no yaiba",
    "my hero academia", "boku no hero academia", "fullmetal alchemist",
    "fullmetal alchemist brotherhood", "death note", "code geass",
    "steins;gate", "sword art online", "tokyo ghoul", "one punch man",
    "mob psycho 100", "hunter x hunter", "gintama", "fairy tail",
    "dragon ball", "dragon ball z", "dragon ball super", "pokemon",
    "yu-gi-oh", "digimon", "sailor moon", "cardcaptor sakura",
    "evangelion", "cowboy bebop", "samurai champloo", "trigun",
    "berserk", "hellsing", "black lagoon", "ghost in the shell",
    "akira", "spirited away", "howl's moving castle", "princess mononoke",
    "your name", "kimi no na wa", "weathering with you", "tenki no ko",
    "silent voice", "koe no katachi", "garden of words", "kotonoha no niwa",
    "5 centimeters per second", "byousoku 5 centimeter",
    "clannad", "air", "kanon", "angel beats", "little busters",
    "re:zero", "konosuba", "overlord", "saga of tanya the evil",
    "gate", "dr. stone", "fire force", "en en no shouboutai",
    "jujutsu kaisen", "chainsaw man", "spy x family", "ranking of kings",
    "oshi no ko", "frieren", "sousou no frieren", "apothecary diaries",
    "kusuriya no hitorigoto", "dungeon meshi", "delicious in dungeon",
    "solo leveling", "tower of god", "god of high school", "noblesse",
    "the rising of the shield hero", "that time i got reincarnated as a slime",
    "tensei shitara slime datta ken", "mushoku tensei", "jobless reincarnation",
    "the eminence in shadow", "kage no jitsuryokusha", "classroom of the elite",
    "youkoso jitsuryoku shijou shugi no kyoushitsu e", "kaguya-sama",
    "love is war", "kaguya-sama wa kokurasetai", "haikyuu",
    "kuroko no basket", "free!", "yuri on ice", "sk8 the infinity",
    "given", "banana fish", "no. 6", "sarazanmai", "devilman crybaby",
    "beastars", "bna", "great pretender", "carole & tuesday",
    "dorohedoro", "made in abyss", "the promised neverland",
    "yakusoku no neverland", "erased", "boku dake ga inai machi",
    "steins;gate 0", "psycho-pass", "monster", "pluto", "20th century boys",
    "vagabond", "berserk", "vinland saga", "vinland saga",
    "kingdom", "ragna crimson", "kaiju no. 8", "dandadan"
}

# Keywords that strongly suggest anime (even if title not in list)
ANIME_KEYWORDS = {
    "anime", "shonen", "shounen", "seinen", "shoujo", "josei",
    "slice of life", "mecha", "isekai", "magical girl", "mahou shoujo",
    "school", "romance", "comedy", "drama", "fantasy", "supernatural",
    "action", "adventure", "sci-fi", "sci fi", "ecchi", "harem",
    "yaoi", "yuri", "gender bender", "harem", "reverse harem"
}

def _load_anime_list() -> Set[str]:
    """Load anime titles from JSON file (anime_titles.json) or fallback to built-in set."""
    # Try to load from external file for extensibility
    json_path = os.path.join(os.path.dirname(__file__), "anime_titles.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(title.lower() for title in data)
            elif isinstance(data, dict) and "titles" in data:
                return set(title.lower() for title in data["titles"])
            else:
                logger.warning("anime_titles.json has unexpected format, using defaults")
    except FileNotFoundError:
        logger.debug("anime_titles.json not found, using built-in anime list")
    except Exception as e:
        logger.warning(f"Failed to load anime_titles.json: {e}")

    # Fallback to built-in list
    return DEFAULT_ANIME_TITLES.copy()

ANIME_TITLES = _load_anime_list()
if not ANIME_TITLES:
    ANIME_TITLES = set()


# ---------- Episode pattern parsing ----------
EPISODE_PATTERNS = [
    # S02E08, S2E8
    re.compile(r'(?i)[Ss](\d{1,2})[Ee](\d{1,3})'),
    # Season 2 Episode 8, season 02 episode 08
    re.compile(r'(?i)season\s*(\d{1,2})\s*(?:episode|ep)\s*(\d{1,3})'),
    # E120, Ep120, Episode-12
    re.compile(r'(?i)(?:[Ee]p(?:isode)?)[\s\-]?(\d{1,4})'),
    # Volume/Chapter? Not typical but added for completeness
    re.compile(r'(?i)(?:vol|volume|chapter)[\s\-]?(\d{1,4})'),
]

def parse_episode_info(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Scan text for season/episode patterns.
    Returns (season, episode) or (None, None).
    """
    if not text:
        return None, None
    for pat in EPISODE_PATTERNS:
        match = pat.search(text)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                try:
                    season = int(groups[0])
                    episode = int(groups[1])
                    return season, episode
                except ValueError:
                    continue
            elif len(groups) == 1:
                try:
                    episode = int(groups[0])
                    return None, episode
                except ValueError:
                    continue
    return None, None


# ---------- Language detection ----------
LANGUAGE_KEYWORDS = {
    'hindi': 'hi',
    'tamil': 'ta',
    'telugu': 'te',
    'english': 'en',
    'japanese': 'ja',
    'korean': 'ko',
    'chinese': 'zh',
    'spanish': 'es',
    'french': 'fr',
    'german': 'de',
    'italian': 'it',
    'portuguese': 'pt',
    'russian': 'ru',
    'arabic': 'ar',
    'indonesian': 'id',
    'thai': 'th',
    'vietnamese': 'vi',
    'dual audio': 'dual',
    'multi audio': 'multi',
    'multi-audio': 'multi',
    'dubbed': 'dub',
    'subbed': 'sub',
}

def detect_languages(text: str) -> List[str]:
    """
    Return a list of ISO language codes (or special tokens like 'dual', 'multi')
    found in the given text.
    """
    if not text:
        return []
    text_lower = text.lower()
    found = set()
    # Check for explicit language keywords
    for keyword, code in LANGUAGE_KEYWORDS.items():
        if keyword in text_lower:
            found.add(code)
    # Also check for patterns like "Hindi + Tamil + Telugu"
    for sep in ['+', '&', ',']:
        if sep in text_lower:
            parts = text_lower.split(sep)
            for part in parts:
                part = part.strip()
                for keyword, code in LANGUAGE_KEYWORDS.items():
                    if keyword in part:
                        found.add(code)
    # Remove duplicate 'dual' and 'multi' if specific languages also present?
    # Keep them all.
    return list(found)


# ---------- Subtype detection (for anime) ----------
ANIME_SUBTYPE_KEYWORDS = {
    'ova': 'OVA',
    'ona': 'ONA',
    'movie': 'Movie',
    'special': 'Special',
    'final season': 'Final Season',
    'part 2': 'Part 2',
    'part ii': 'Part 2',
    'part 3': 'Part 3',
    'part iii': 'Part 3',
    'part iv': 'Part 4',
    'part v': 'Part 5',
}

def detect_anime_subtype(title: str) -> Optional[str]:
    """Return subtype string if found, else None."""
    if not title:
        return None
    title_lower = title.lower()
    for key, subtype in ANIME_SUBTYPE_KEYWORDS.items():
        if key in title_lower:
            return subtype
    return None


# ---------- Quality detection (optional) ----------
QUALITY_PATTERNS = [
    re.compile(r'\b(1080p|1080|full hd|fhd)\b', re.IGNORECASE),
    re.compile(r'\b(720p|720|hd ready)\b', re.IGNORECASE),
    re.compile(r'\b(480p|480|sd)\b', re.IGNORECASE),
    re.compile(r'\b(2160p|4k|uhd)\b', re.IGNORECASE),
]

def detect_quality(text: str) -> Optional[str]:
    """Extract quality (e.g., '1080p', '720p') from text."""
    if not text:
        return None
    for pat in QUALITY_PATTERNS:
        match = pat.search(text)
        if match:
            return match.group(0).lower()
    return None


# ---------- Main detection function ----------
def detect(extracted: ExtractedContent) -> ContentType:
    """
    Determine content type and also populate extracted.subtype, extracted.languages,
    extracted.quality, and season/episode if missing.
    """
    if extracted.title is None:
        logger.debug("Title is None, cannot classify.")
        return ContentType.UNKNOWN

    title = extracted.title.strip()
    title_lower = title.lower()
    logger.debug(f"Classifying title: '{title}'")

    # ----- 1. Parse season/episode if not already present -----
    if extracted.season is None and extracted.episode is None:
        season, episode = parse_episode_info(title)
        if season is not None or episode is not None:
            extracted.season = season
            extracted.episode = episode
            logger.debug(f"Parsed season={season}, episode={episode} from title")

    # ----- 2. Detect quality if not already present -----
    if not extracted.quality:
        quality = detect_quality(title)
        if quality:
            extracted.quality = quality
            logger.debug(f"Detected quality: {quality}")

    # ----- 3. Detect languages from title if not already set -----
    if not extracted.languages:
        langs = detect_languages(title)
        if langs:
            extracted.languages = langs
            logger.debug(f"Detected languages from title: {langs}")

    # ----- 4. TV detection via season/episode -----
    if extracted.season is not None or extracted.episode is not None:
        logger.info(f"Detected TV show (season/episode present): '{title}'")
        # Check if anime (either in list or keyword)
        is_anime = (title_lower in ANIME_TITLES or any(kw in title_lower for kw in ANIME_KEYWORDS))
        if is_anime:
            subtype = detect_anime_subtype(title)
            extracted.subtype = subtype
            # Even if subtype is Movie, we keep as ANIME because it's anime content.
            logger.info(f"Anime subtype: {subtype}")
            return ContentType.ANIME
        else:
            return ContentType.TV

    # ----- 5. Anime detection (no season/episode) -----
    if title_lower in ANIME_TITLES:
        extracted.subtype = detect_anime_subtype(title)
        logger.info(f"Detected anime (exact match): '{title}', subtype={extracted.subtype}")
        return ContentType.ANIME

    for keyword in ANIME_KEYWORDS:
        if keyword in title_lower:
            extracted.subtype = detect_anime_subtype(title)
            logger.info(f"Detected anime (keyword '{keyword}'): '{title}', subtype={extracted.subtype}")
            return ContentType.ANIME

    # ----- 6. Fallback to movie -----
    logger.info(f"Detected movie (fallback): '{title}'")
    return ContentType.MOVIE


# ---------- Example usage and test ----------
if __name__ == "__main__":
    # Configure logging for test
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    test_cases = [
        # (title, expected_type, expected_subtype, expected_season, expected_episode)
        ("Naruto Shippuden S02E08", ContentType.ANIME, None, 2, 8),
        ("Attack on Titan Final Season Part 2", ContentType.ANIME, "Final Season", None, None),
        ("Demon Slayer: Mugen Train Movie", ContentType.ANIME, "Movie", None, None),
        ("Jujutsu Kaisen 0", ContentType.ANIME, "Movie", None, None),
        ("The Office S05E12", ContentType.TV, None, 5, 12),
        ("Inception 2010", ContentType.MOVIE, None, None, None),
        ("Spy x Family Episode 24", ContentType.ANIME, None, None, 24),
        ("Dragon Ball Z - Season 3", ContentType.ANIME, None, 3, None),
        ("Unknown Movie 2023", ContentType.MOVIE, None, None, None),
        ("One Piece (2023) 1080p Hindi + English", ContentType.ANIME, None, None, None),
    ]

    for title, exp_type, exp_sub, exp_season, exp_ep in test_cases:
        content = ExtractedContent(title=title)
        detected = detect(content)
        print(f"Title: {title}")
        print(f"  Detected: {detected.value}, subtype: {content.subtype}, season: {content.season}, episode: {content.episode}, languages: {content.languages}, quality: {content.quality}")
        assert detected == exp_type, f"Expected {exp_type}, got {detected}"
        if exp_sub is not None:
            assert content.subtype == exp_sub, f"Expected subtype {exp_sub}, got {content.subtype}"
        if exp_season is not None:
            assert content.season == exp_season, f"Expected season {exp_season}, got {content.season}"
        if exp_ep is not None:
            assert content.episode == exp_ep, f"Expected episode {exp_ep}, got {content.episode}"
        print("  OK")
    print("All tests passed!")
    
