"""
Content type detector for movies, TV shows, and anime.

Enhanced with:
- Subtype detection (OVA, ONA, Movie, Special, Final Season, Part 2)
- Fallback season/episode parsing from title (E120, S02E08, Season 2, etc.)
- Language detection from text
- Quality detection (optional)
- Robust anime and TV title matching from built‑in lists and external JSON files
- Year‑based clues for movie classification
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
    from metadata.extractor import ExtractedContent
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

def _load_anime_list() -> Set[str]:
    """Load anime titles from JSON file or fallback to built‑in set."""
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
        logger.debug("anime_titles.json not found, using built‑in anime list")
    except Exception as e:
        logger.warning(f"Failed to load anime_titles.json: {e}")
    return DEFAULT_ANIME_TITLES.copy()

ANIME_TITLES = _load_anime_list()
if not ANIME_TITLES:
    ANIME_TITLES = set()


# ---------- TV data ----------
DEFAULT_TV_TITLES = {
    "the office", "friends", "breaking bad", "game of thrones", "stranger things",
    "the walking dead", "better call saul", "the crown", "the mandalorian",
    "westworld", "black mirror", "the witcher", "the boys", "succession",
    "house of the dragon", "the last of us", "true detective", "fargo",
    "mindhunter", "ozark", "the bear", "only murders in the building",
    "the good place", "brooklyn nine-nine", "parks and recreation",
    "the big bang theory", "how i met your mother", "two and a half men",
    "modern family", "the simpsons", "family guy", "south park",
    "rick and morty", "the x-files", "twin peaks", "the sopranos",
    "the wire", "mad men", "lost", "heroes", "prison break", "24",
    "the west wing", "the newsroom", "the americans", "homeland",
    "the handmaid's tale", "the expanse", "the peripheral", "altered carbon"
}

def _load_tv_list() -> Set[str]:
    """Load TV titles from JSON file or fallback to built‑in set."""
    json_path = os.path.join(os.path.dirname(__file__), "tv_titles.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(title.lower() for title in data)
            elif isinstance(data, dict) and "titles" in data:
                return set(title.lower() for title in data["titles"])
            else:
                logger.warning("tv_titles.json has unexpected format, using defaults")
    except FileNotFoundError:
        logger.debug("tv_titles.json not found, using built‑in TV list")
    except Exception as e:
        logger.warning(f"Failed to load tv_titles.json: {e}")
    return DEFAULT_TV_TITLES.copy()

TV_TITLES = _load_tv_list()
if not TV_TITLES:
    TV_TITLES = set()


# ---------- Episode/season parsing ----------
EPISODE_PATTERNS = [
    # S02E08, S2E8
    re.compile(r'(?i)[Ss](\d{1,2})[Ee](\d{1,3})'),
    # Season 2 Episode 8, season 02 episode 08
    re.compile(r'(?i)season\s*(\d{1,2})\s*(?:episode|ep)\s*(\d{1,3})'),
    # E120, Ep120, Episode-12
    re.compile(r'(?i)(?:[Ee]p(?:isode)?)[\s\-]?(\d{1,4})'),
    # Standalone season: Season 2, S02, S2 (but avoid matching S02E08 already handled)
    re.compile(r'(?i)season\s*(\d{1,2})'),
    re.compile(r'(?i)[Ss](\d{1,2})(?![Ee])'),
    # Volume/Chapter (uncommon)
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
                    # Could be season or episode depending on pattern
                    # For standalone season patterns, we return (season, None)
                    # For episode-only patterns, we return (None, episode)
                    # We need to distinguish: we can check if pattern is season pattern
                    # We'll use a heuristic: if the matched pattern contains "season" or "S" (without E), it's season
                    # However, we can't easily tell from match object; we'll check the pattern string
                    # Instead, we use the fact that the pattern for standalone season is either "season" or "S" without "E"
                    # Let's examine the match: we can get the pattern from the compiled regex, but it's not straightforward.
                    # Simpler: we can try to interpret as season if the matched text contains "season" or "s" and no "e"
                    # But "S02" could be ambiguous. We'll prioritize episode-only patterns (they are earlier) and then season-only.
                    # The current order: after combined patterns, we have season-only patterns.
                    # But we also have episode-only pattern E120 etc. That comes before season-only.
                    # So if we hit episode-only, we return (None, episode).
                    # If we hit season-only, we return (season, None).
                    # However, we cannot know which pattern matched. We'll use a crude method:
                    # For the "E" and "Episode" patterns, they are episode-only; for season patterns they are season-only.
                    # We can check the pattern's string, but it's messy.
                    # Better: we'll restructure: we'll have separate functions for episode and season.
                    pass
                except ValueError:
                    continue
    # Fallback: if none matched, return None
    return None, None


# Improved parse function that distinguishes season and episode
def parse_season_episode(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Enhanced parsing: returns (season, episode) with season-only or episode-only detection.
    """
    if not text:
        return None, None

    text_lower = text.lower()

    # First try combined patterns
    combined_pats = [
        re.compile(r'(?i)[Ss](\d{1,2})[Ee](\d{1,3})'),
        re.compile(r'(?i)season\s*(\d{1,2})\s*(?:episode|ep)\s*(\d{1,3})'),
    ]
    for pat in combined_pats:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1)), int(m.group(2))
            except ValueError:
                continue

    # Episode-only patterns
    ep_pats = [
        re.compile(r'(?i)(?:[Ee]p(?:isode)?)[\s\-]?(\d{1,4})'),
    ]
    for pat in ep_pats:
        m = pat.search(text)
        if m:
            try:
                return None, int(m.group(1))
            except ValueError:
                continue

    # Season-only patterns (standalone)
    season_pats = [
        re.compile(r'(?i)season\s*(\d{1,2})'),
        re.compile(r'(?i)[Ss](\d{1,2})(?![Ee])'),  # S followed by digits, not followed by E
    ]
    for pat in season_pats:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1)), None
            except ValueError:
                continue

    # Volume/Chapter (treat as episode)
    vol_pat = re.compile(r'(?i)(?:vol|volume|chapter)[\s\-]?(\d{1,4})')
    m = vol_pat.search(text)
    if m:
        try:
            return None, int(m.group(1))
        except ValueError:
            pass

    return None, None


# Override original parse_episode_info to use enhanced version
parse_episode_info = parse_season_episode


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
    if not text:
        return []
    text_lower = text.lower()
    found = set()
    for keyword, code in LANGUAGE_KEYWORDS.items():
        if keyword in text_lower:
            found.add(code)
    for sep in ['+', '&', ',']:
        if sep in text_lower:
            parts = text_lower.split(sep)
            for part in parts:
                part = part.strip()
                for keyword, code in LANGUAGE_KEYWORDS.items():
                    if keyword in part:
                        found.add(code)
    return list(found)


# ---------- Subtype detection ----------
ANIME_SUBTYPE_KEYWORDS = {
    'ova': 'OVA',
    'ona': 'ONA',
    'movie': 'Movie',
    'film': 'Movie',
    'special': 'Special',
    'final season': 'Final Season',
    'part 2': 'Part 2',
    'part ii': 'Part 2',
    'part 3': 'Part 3',
    'part iii': 'Part 3',
    'part iv': 'Part 4',
    'part v': 'Part 5',
    # Additional variants
    'final season part 2': 'Final Season',
    'final season part ii': 'Final Season',
}

def detect_anime_subtype(title: str) -> Optional[str]:
    if not title:
        return None
    title_lower = title.lower()
    # Check exact phrases first
    for key, subtype in ANIME_SUBTYPE_KEYWORDS.items():
        if key in title_lower:
            return subtype
    return None


# ---------- Quality detection ----------
QUALITY_PATTERNS = [
    re.compile(r'\b(1080p|1080|full hd|fhd)\b', re.IGNORECASE),
    re.compile(r'\b(720p|720|hd ready)\b', re.IGNORECASE),
    re.compile(r'\b(480p|480|sd)\b', re.IGNORECASE),
    re.compile(r'\b(2160p|4k|uhd)\b', re.IGNORECASE),
]

def detect_quality(text: str) -> Optional[str]:
    if not text:
        return None
    for pat in QUALITY_PATTERNS:
        match = pat.search(text)
        if match:
            return match.group(0).lower()
    return None


# ---------- TV keywords ----------
TV_KEYWORDS = {
    "tv series", "tv show", "television series", "series", "show",
    "complete series", "full series", "all seasons", "season pack",
    "box set"
}

def is_tv_keyword_in_title(title: str) -> bool:
    """Return True if the title contains any TV keyword."""
    if not title:
        return False
    lower = title.lower()
    for kw in TV_KEYWORDS:
        if kw in lower:
            return True
    return False


# ---------- Main detection function ----------
def detect(extracted: ExtractedContent) -> ContentType:
    """
    Determine content type and populate extracted.subtype, .languages,
    .quality, and season/episode if missing.
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

    # ----- 4. Season/episode present: TV or Anime -----
    if extracted.season is not None or extracted.episode is not None:
        # Check if anime
        is_anime = (title_lower in ANIME_TITLES or any(kw in title_lower for kw in ANIME_KEYWORDS))
        if is_anime:
            subtype = detect_anime_subtype(title)
            extracted.subtype = subtype
            logger.info(f"Anime with season/ep: '{title}', subtype={subtype}")
            return ContentType.ANIME
        else:
            # If it has a season/episode, it's TV (unless anime)
            logger.info(f"TV show with season/ep: '{title}'")
            return ContentType.TV

    # ----- 5. Anime detection (no season/ep) -----
    if title_lower in ANIME_TITLES:
        extracted.subtype = detect_anime_subtype(title)
        logger.info(f"Anime (exact match): '{title}', subtype={extracted.subtype}")
        return ContentType.ANIME

    for keyword in ANIME_KEYWORDS:
        if keyword in title_lower:
            extracted.subtype = detect_anime_subtype(title)
            logger.info(f"Anime (keyword '{keyword}'): '{title}', subtype={extracted.subtype}")
            return ContentType.ANIME

    # ----- 6. TV detection (no season/ep) -----
    # Check exact title in TV list
    if title_lower in TV_TITLES:
        logger.info(f"TV show (exact match): '{title}'")
        return ContentType.TV

    # Check for TV keywords
    if is_tv_keyword_in_title(title):
        logger.info(f"TV show (keyword): '{title}'")
        return ContentType.TV

    # ----- 7. Movie detection -----
    # If year is present (and not too far in future), it's likely a movie
    if extracted.year is not None and 1900 <= extracted.year <= 2030:
        logger.info(f"Movie (year present): '{title}'")
        return ContentType.MOVIE

    # Look for 'movie' or 'film' in title
    if re.search(r'\b(?:movie|film)\b', title_lower):
        logger.info(f"Movie (keyword): '{title}'")
        return ContentType.MOVIE

    # ----- 8. Fallback: still movie (legacy) but log warning -----
    logger.warning(f"Fallback to MOVIE for unknown content: '{title}'")
    return ContentType.MOVIE


# ---------- Example usage and test ----------
if __name__ == "__main__":
    # Configure logging for test
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    test_cases = [
        # (title, year, expected_type, expected_subtype, expected_season, expected_episode)
        ("Naruto Shippuden S02E08", None, ContentType.ANIME, None, 2, 8),
        ("Attack on Titan Final Season Part 2", None, ContentType.ANIME, "Final Season", None, None),
        ("Demon Slayer: Mugen Train Movie", None, ContentType.ANIME, "Movie", None, None),
        ("Jujutsu Kaisen 0", None, ContentType.ANIME, "Movie", None, None),
        ("The Office S05E12", None, ContentType.TV, None, 5, 12),
        ("Inception 2010", 2010, ContentType.MOVIE, None, None, None),
        ("Spy x Family Episode 24", None, ContentType.ANIME, None, None, 24),
        ("Dragon Ball Z - Season 3", None, ContentType.ANIME, None, 3, None),  # standalone season
        ("Unknown Movie 2023", 2023, ContentType.MOVIE, None, None, None),
        ("One Piece (2023) 1080p Hindi + English", None, ContentType.ANIME, None, None, None),
        ("The Office", None, ContentType.TV, None, None, None),  # now TV
        ("Breaking Bad Complete Series", None, ContentType.TV, None, None, None),
        ("Stranger Things Season 2", None, ContentType.TV, None, 2, None),  # standalone season
        ("The Bear", None, ContentType.TV, None, None, None),
        ("Dune 2021", 2021, ContentType.MOVIE, None, None, None),
        ("The Matrix", None, ContentType.MOVIE, None, None, None),  # falls back to movie
    ]

    for item in test_cases:
        title, year, exp_type, exp_sub, exp_season, exp_ep = item
        content = ExtractedContent(title=title, year=year)
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
    
