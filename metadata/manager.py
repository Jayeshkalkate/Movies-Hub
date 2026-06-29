# manager.py
"""
Main orchestration manager for content discovery and caching.

This module ties together the extraction, detection, caching, and provider
fetching layers to deliver a complete metadata pipeline from a Telegram caption.

Workflow:
    1. Extract structured data from caption (title, year, etc.)
    2. Detect content type (movie, tv, anime, unknown) and augment with
       episode/season patterns, language hints, and anime subtypes.
    3. Check cache by title (and optionally year/type and telegram_file_id).
    4. If cached, return metadata.
    5. Else, query ALL providers (TMDb Movie, TMDb TV, TVMaze, AniList, Jikan),
       collect results, compute a confidence score for each, and pick the best.
    6. Format the raw response into the common schema.
    7. Save to cache (upsert by telegram_file_id if provided).
    8. Return the metadata.

All external dependencies are injected via constructor for testability.
"""

import logging
import re
import traceback
from difflib import SequenceMatcher
from typing import Optional, Dict, Any, Callable, List, Tuple

# ---------------------------------------------------------------------
# Adjust imports to match your project structure.
# If any module is missing, define a stub or install the required package.
# ---------------------------------------------------------------------
from .extractor import extract, ExtractedContent
from .tmdb_cache import save_metadata, find_by_title
from .detector import detect, ContentType, detect_languages
from .formatter import (
    format_tmdb,
    format_tvmaze,
    format_jikan,
    format_anilist,
)
from .providers.tmdb import (
    TMDbClient,
    get_tmdb_client,
    TMDbError,
)
from .providers.tvmaze import (
    TVMazeClient,
    get_tvmaze_client,
    TVMazeError,
)
from .providers.jikan import (
    JikanClient,
    get_jikan_client,
    JikanError,
)
from .providers.anilist import (
    AniListClient,
    get_anilist_client,
    AniListError,
)

# ---------------------------------------------------------------------
# Fallback for movie_parser.clean_text if not available
# ---------------------------------------------------------------------
try:
    from coremovieshub.utils.movie_parser import clean_text
except ImportError:
    def clean_text(text: str) -> str:
        """Remove extra whitespace, lower-case, and strip common noise."""
        if not text:
            return ""
        # Remove file extensions, replace underscores/dots with spaces
        cleaned = re.sub(r'\.[a-zA-Z0-9]{2,4}$', '', text)
        cleaned = re.sub(r'[._]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip()

logger = logging.getLogger(__name__)


class Manager:
    """
    Main orchestration class for content metadata retrieval.

    Uses a fallback chain of providers to maximize hit rate, regardless of
    initial content type detection.

    Attributes:
        tmdb_client: TMDb client instance.
        tvmaze_client: TVMaze client instance.
        jikan_client: Jikan client instance.
        anilist_client: AniList client instance.
        find_by_title_fn: Cache lookup function.
        find_by_external_id_fn: Optional cache lookup by ID.
        save_metadata_fn: Cache save function.
        extractor_fn: Extraction function.
        detector_fn: Detection function.
        format_tmdb_fn: TMDb formatter function.
        format_tvmaze_fn: TVMaze formatter function.
        format_jikan_fn: Jikan formatter function.
        format_anilist_fn: AniList formatter function.
    """

    # Provider order – we query all, but scoring decides the best.
    PROVIDER_CHAIN = [
        "tmdb_movie",
        "tmdb_tv",
        "anilist",
        "jikan",
        "tvmaze",
    ]

    def __init__(
        self,
        tmdb_client: Optional[TMDbClient] = None,
        tvmaze_client: Optional[TVMazeClient] = None,
        jikan_client: Optional[JikanClient] = None,
        anilist_client: Optional[AniListClient] = None,
        find_by_title_fn: Callable = find_by_title,
        find_by_external_id_fn: Optional[Callable] = None,
        save_metadata_fn: Callable = save_metadata,
        extractor_fn: Callable = extract,
        detector_fn: Callable = detect,
        format_tmdb_fn: Callable = format_tmdb,
        format_tvmaze_fn: Callable = format_tvmaze,
        format_jikan_fn: Callable = format_jikan,
        format_anilist_fn: Callable = format_anilist,
    ):
        """
        Initialize the Manager with optional injected dependencies.

        If a client is not provided, the default factory function is used.
        """
        self.tmdb_client = tmdb_client or get_tmdb_client()
        self.tvmaze_client = tvmaze_client or get_tvmaze_client()
        self.jikan_client = jikan_client or get_jikan_client()
        self.anilist_client = anilist_client or get_anilist_client()

        self.find_by_title_fn = find_by_title_fn
        self.find_by_external_id_fn = find_by_external_id_fn
        self.save_metadata_fn = save_metadata_fn

        self.extractor_fn = extractor_fn
        self.detector_fn = detector_fn

        self.format_tmdb_fn = format_tmdb_fn
        self.format_tvmaze_fn = format_tvmaze_fn
        self.format_jikan_fn = format_jikan_fn
        self.format_anilist_fn = format_anilist_fn

    # ---------- Helper: generate text variants ----------
    def _get_caption_variants(self, text: str) -> List[str]:
        """
        Generate alternative versions of the input text to improve extraction chances.
        Returns a list of strings, the original text first.
        """
        variants = [text]  # always try the original first

        # 1. First line only (often contains the main title)
        first_line = text.split('\n')[0].strip()
        if first_line and first_line != text:
            variants.append(first_line)

        # 2. Remove common release-group tags (e.g., [WEBRip], [x264], etc.)
        cleaned = re.sub(r'\[[^\]]+\]', '', text)  # removes [tag]
        cleaned = re.sub(r'\([^)]+\)', '', cleaned)   # removes (tag)
        cleaned = re.sub(r'\{[^}]+\}', '', cleaned)   # removes {tag}
        cleaned = ' '.join(cleaned.split())           # collapse whitespace
        if cleaned and cleaned != text:
            variants.append(cleaned)

        # 3. Text before the first year (e.g., "Movie Title 2024" -> "Movie Title")
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            before_year = text[:year_match.start()].strip()
            # Also remove trailing punctuation or separators
            before_year = re.sub(r'[:\-–—|•·]+$', '', before_year).strip()
            if before_year and before_year != text:
                variants.append(before_year)

        # 4. If the text is very long, take a substring up to a reasonable length
        #    (sometimes the title is at the very beginning)
        if len(text) > 80:
            short = text[:80].rsplit(' ', 1)[0]  # cut at word boundary
            if short and short != text:
                variants.append(short)

        # Remove duplicates while preserving order
        seen = set()
        unique_variants = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                unique_variants.append(v)
        return unique_variants

    # ---------- Query a single provider and format ----------
    def _search_and_format(
        self,
        provider_type: str,
        title: str,
        year: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        """
        Query a specific provider and format the result.

        Args:
            provider_type: One of 'tmdb_movie', 'tmdb_tv', 'tvmaze',
                           'anilist', 'jikan'.
            title: Search title (already normalized).
            year: Optional year filter (used where supported).

        Returns:
            Optional[Dict[str, Any]]: Formatted metadata or None if no results.

        Raises:
            Provider-specific exceptions (caught by caller).
        """
        raw_response = None
        formatted = None

        if provider_type == "tmdb_movie":
            logger.info("Searching TMDB | title=%s | year=%s", title, year)
            raw_response = self.tmdb_client.search_movie(title, year=year)
            results = raw_response.get("results", [])
            if results:
                first = results[0]
                formatted = self.format_tmdb_fn(first, content_type="movie")
            else:
                logger.debug(f"No TMDb movie results for '{title}'")
                return None

        elif provider_type == "tmdb_tv":
            logger.info("Searching TMDB | title=%s | year=%s", title, year)
            raw_response = self.tmdb_client.search_tv(title, first_air_date_year=year)
            results = raw_response.get("results", [])
            if results:
                first = results[0]
                formatted = self.format_tmdb_fn(first, content_type="tv")
            else:
                logger.debug(f"No TMDb TV results for '{title}'")
                return None

        elif provider_type == "tvmaze":
            raw_response = self.tvmaze_client.search_show(title)
            if raw_response:
                first = raw_response[0]
                formatted = self.format_tvmaze_fn(first)
            else:
                logger.debug(f"No TVMaze results for '{title}'")
                return None

        elif provider_type == "anilist":
            raw_response = self.anilist_client.search_anime(
                title=title,
                year=year,
                per_page=1,
            )
            data = raw_response.get("data", {})
            page = data.get("Page", {})
            media_list = page.get("media", [])
            if media_list:
                first = media_list[0]
                formatted = self.format_anilist_fn(first)
            else:
                logger.debug(f"No AniList results for '{title}'")
                return None

        elif provider_type == "jikan":
            raw_response = self.jikan_client.search_anime(title, year=year)
            results = raw_response.get("data", [])
            if results:
                first = results[0]
                formatted = self.format_jikan_fn(first)
            else:
                logger.debug(f"No Jikan results for '{title}'")
                return None

        else:
            raise ValueError(f"Unknown provider_type: {provider_type}")

        # Ensure we have a valid result with an external ID
        if formatted and formatted.get("external_id"):
            # Attach the provider name for scoring
            formatted["_provider"] = provider_type
            return formatted
        else:
            logger.warning(f"Provider {provider_type} returned incomplete data for '{title}'")
            return None

    # ---------- Confidence scoring ----------
    def _compute_score(
        self,
        metadata: Dict[str, Any],
        extracted: ExtractedContent,
        search_title: str,
    ) -> float:
        """
        Compute a confidence score (0-1) for a metadata result.

        Factors:
            - Title similarity (0.4)
            - Year match (0.3)
            - Content type match (0.15)
            - Language match (0.10)
            - Popularity / vote average (0.05)

        Returns:
            float: Score between 0 and 1.
        """
        score = 0.0

        # 1. Title similarity (0-0.4)
        meta_title = metadata.get("title", "")
        if meta_title:
            sim = SequenceMatcher(None, search_title.lower(), meta_title.lower()).ratio()
            score += sim * 0.4

        # 2. Year match (0-0.3)
        search_year = extracted.year
        if search_year and metadata.get("release_date"):
            try:
                meta_year = int(metadata["release_date"][:4])
                if meta_year == search_year:
                    score += 0.3
                elif abs(meta_year - search_year) <= 1:
                    score += 0.15
            except (ValueError, TypeError):
                pass

        # 3. Content type match (0-0.15)
        expected_type = getattr(extracted, 'content_type', None)
        if expected_type and metadata.get("content_type"):
            if metadata["content_type"] == expected_type.value:
                score += 0.15
            # If expected is anime and we got tv, partial
            elif expected_type == ContentType.ANIME and metadata["content_type"] == "tv":
                score += 0.05

        # 4. Language match (0-0.10)
        expected_langs = set(extracted.languages or [])
        meta_langs = set(metadata.get("languages") or [])
        if expected_langs and meta_langs:
            common = expected_langs & meta_langs
            if common:
                score += 0.10 * (len(common) / max(len(expected_langs), len(meta_langs)))

        # 5. Popularity (0-0.05)
        if metadata.get("vote_average") is not None:
            try:
                pop = float(metadata["vote_average"]) / 10.0  # normalize 0-1
                score += pop * 0.05
            except (TypeError, ValueError):
                pass

        logger.debug(f"Score for {metadata.get('_provider')}: {score:.3f}")
        return score

    # ---------- Fetch from all providers and pick best ----------
    def _fetch_and_cache(
        self,
        extracted: ExtractedContent,
        content_type: ContentType,
        telegram_file_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Query ALL providers, score results, pick the best, and cache it.

        Args:
            extracted: Extracted content info.
            content_type: Detected content type (used for logging).
            telegram_file_id: Optional unique ID for cache upsert.

        Returns:
            Optional[Dict[str, Any]]: Best metadata or None.
        """
        title = extracted.title
        year = extracted.year

        if not title:
            logger.warning("Cannot fetch: missing title")
            return None

        # Normalize title for provider searches
        search_title = clean_text(title)
        if not search_title:
            logger.warning(f"Title became empty after normalization, using original '{title}'")
            search_title = title
        else:
            logger.debug(f"Normalized title for search: '{search_title}' (original: '{title}')")

        logger.info(f"Fetching '{title}' (detected as {content_type.value}) "
                    f"from {len(self.PROVIDER_CHAIN)} providers")

        candidates = []

        for provider in self.PROVIDER_CHAIN:
            try:
                logger.debug(f"Querying {provider}...")
                metadata = self._search_and_format(provider, search_title, year)
                if metadata and metadata.get("external_id"):
                    # Compute score for this candidate
                    metadata["_score"] = self._compute_score(metadata, extracted, search_title)
                    candidates.append(metadata)
                else:
                    logger.debug(f"{provider} returned no valid result")
            except (TMDbError, TVMazeError, JikanError, AniListError) as e:
                logger.warning(f"{provider} failed: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error from {provider}: {e}")
                continue

        if not candidates:
            logger.warning(f"No provider returned data for '{search_title}'")
            return None

        # Pick best by score
        best = max(candidates, key=lambda x: x.get("_score", 0.0))
        best_score = best.get("_score", 0.0)
        best_provider = best.get("_provider", "unknown")

        # --- Improved logging after choosing the best match ---
        logger.info(
            "Matched TMDB | %s (%s) | score=%s",
            best.get("title"),
            best.get("external_id"),
            best_score,
        )

        # Optional: if best_score is very low, we might still return it,
        # but we could add a threshold if needed.

        # Cache it (upsert by telegram_file_id if provided)
        try:
            # Add telegram_file_id to metadata for upsert
            if telegram_file_id:
                best["telegram_file_id"] = telegram_file_id
            # --- Improved logging before saving ---
            logger.info("Caching TMDB %s", best.get("external_id"))
            self.save_metadata_fn(best, telegram_file_id=telegram_file_id)
        except Exception as e:
            logger.exception(f"Failed to cache metadata: {e}")

        return best

    # ---------- Main entry point ----------
    def process_caption(
        self,
        caption: str,
        filename: Optional[str] = None,
        telegram_file_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Main entry point: process a Telegram caption (and optional filename)
        and return metadata.

        Args:
            caption: The raw caption text.
            filename: Optional filename (e.g., from a torrent or file name)
                      to improve extraction.
            telegram_file_id: Optional unique ID from Telegram for cache upsert.

        Returns:
            Optional[Dict[str, Any]]: The metadata in the common schema,
                                      or None if not found.
        """
        # Combine filename and caption if filename is provided
        if filename:
            search_text = f"{filename} {caption}".strip()
            logger.info(f"Processing combined text (filename + caption): {search_text[:100]}...")
        else:
            search_text = caption
            logger.info(f"Processing caption: {caption[:100]}...")

        # Step 1: Try extraction on multiple variants
        variants = self._get_caption_variants(search_text)
        extracted = None
        for idx, variant in enumerate(variants):
            try:
                candidate = self.extractor_fn(variant)
                if isinstance(candidate, ExtractedContent):
                    if candidate.title:
                        extracted = candidate
                        logger.debug(f"Extraction succeeded with variant #{idx}: {variant[:50]}...")
                        break
                elif isinstance(candidate, dict):
                    # If the extractor returns a dict, convert to ExtractedContent
                    # This is a safety net; the default extractor returns ExtractedContent.
                    # But we handle it gracefully.
                    if candidate.get("title"):
                        extracted = ExtractedContent(
                            title=candidate.get("title"),
                            year=candidate.get("year"),
                            season=candidate.get("season"),
                            episode=candidate.get("episode"),
                            quality=candidate.get("quality"),
                            languages=candidate.get("languages") or [],
                            subtype=candidate.get("subtype"),
                            content_type=candidate.get("content_type"),
                        )
                        logger.debug(f"Extraction succeeded (dict) with variant #{idx}: {variant[:50]}...")
                        break
            except Exception as e:
                logger.debug(f"Extraction failed for variant #{idx}: {e}")
                continue

        if not extracted or not extracted.title:
            logger.warning("No title extracted from any text variant")
            return None

        # Step 2: Enhance with language detection from the full search_text
        if not extracted.languages:
            langs = detect_languages(search_text)
            if langs:
                extracted.languages = langs
                logger.debug(f"Detected languages from text: {langs}")

        # Step 3: Detect content type (will also parse episode/season and subtype)
        try:
            content_type = self.detector_fn(extracted)
            # Store type on extracted for scoring
            extracted.content_type = content_type
            logger.info(f"Detected content type: {content_type.value}, "
                        f"subtype: {getattr(extracted, 'subtype', None)}")
        except Exception:
            logger.exception("Detection failed")
            # Fallback to UNKNOWN
            content_type = ContentType.UNKNOWN
            extracted.content_type = content_type

        # Step 4: Check cache
        # Try by telegram_file_id first if provided
        if telegram_file_id and self.find_by_external_id_fn:
            try:
                cached = self.find_by_external_id_fn(telegram_file_id)
                if cached:
                    logger.info(f"Cache hit by telegram_file_id '{telegram_file_id}'")
                    return cached
            except Exception as e:
                logger.warning(f"Cache lookup by telegram_file_id failed: {e}")

        # Then by title/year/type
        try:
            cached = self.find_by_title_fn(
                title=extracted.title,
                content_type=content_type.value if content_type != ContentType.UNKNOWN else None,
                year=extracted.year,
            )
            if cached:
                logger.info(f"Cache hit for title '{extracted.title}'")
                return cached
            else:
                logger.info(f"Cache miss for title '{extracted.title}'")
        except Exception as e:
            logger.warning(f"Cache lookup by title failed: {e}, proceeding with fetch")

        # Step 5: Fetch from providers (with scoring)
        metadata = self._fetch_and_cache(extracted, content_type, telegram_file_id)

        if metadata:
            logger.info(f"Successfully retrieved metadata for '{extracted.title}'")
            return metadata
        else:
            logger.warning(f"No metadata found for '{extracted.title}' after all attempts")
            return None


# ------------------- Convenience function -------------------
def get_manager() -> Manager:
    """
    Factory function to get a Manager instance with default dependencies.

    Returns:
        Manager: Configured manager.
    """
    return Manager()


# ------------------- Example usage -------------------
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Example caption and filename
    caption = "🔥 Pushpa 2 (2024) 1080p WEB-DL Hindi + Telugu"
    filename = "Pushpa.2.The.Rule.2024.1080p.mkv"   # optional

    # Create manager (ensure all providers are configured)
    manager = get_manager()

    # Process with both caption and filename
    result = manager.process_caption(caption, filename=filename)

    if result:
        print("Result:", result)
    else:
        print("No metadata found.")
        
