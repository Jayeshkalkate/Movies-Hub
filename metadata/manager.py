"""
Main orchestration manager for content discovery and caching.

This module ties together the extraction, detection, caching, and provider
fetching layers to deliver a complete metadata pipeline from a Telegram caption.

Workflow:
    1. Extract structured data from caption (title, year, etc.)
    2. Detect content type (movie, tv, anime, unknown) – used for logging/hints
    3. Check cache by title (and optionally year/type)
    4. If cached, return metadata
    5. Else, query providers in a deterministic fallback chain:
        - TMDb Movie search
        - TMDb TV search
        - TVMaze (TV shows)
        - AniList (anime)
        - Jikan (anime)
    6. Format the raw response into the common schema
    7. Save to cache
    8. Return the metadata

All external dependencies are injected via constructor for testability.
"""

import logging
import re
from typing import Optional, Dict, Any, Callable, List, Tuple

from .extractor import extract, ExtractedContent
from .tmdb_cache import (
    save_metadata,
    find_by_title,
)
from .detector import (
    detect,
    ContentType,
)
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

    # Provider order – from most likely to least likely,
    # covering movies, TV, and anime.
    PROVIDER_CHAIN = [
        "tmdb_movie",
        "tmdb_tv",
        "tvmaze",
        "anilist",
        "jikan",
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

    def _get_caption_variants(self, caption: str) -> List[str]:
        """
        Generate alternative versions of the caption to improve extraction chances.
        Returns a list of strings, the original caption first.
        """
        variants = [caption]  # always try the original first

        # 1. First line only (often contains the main title)
        first_line = caption.split('\n')[0].strip()
        if first_line and first_line != caption:
            variants.append(first_line)

        # 2. Remove common release-group tags (e.g., [WEBRip], [x264], etc.)
        cleaned = re.sub(r'\[[^\]]+\]', '', caption)  # removes [tag]
        cleaned = re.sub(r'\([^)]+\)', '', cleaned)   # removes (tag)
        cleaned = re.sub(r'\{[^}]+\}', '', cleaned)   # removes {tag}
        cleaned = ' '.join(cleaned.split())           # collapse whitespace
        if cleaned and cleaned != caption:
            variants.append(cleaned)

        # 3. Text before the first year (e.g., "Movie Title 2024" -> "Movie Title")
        year_match = re.search(r'\b(19|20)\d{2}\b', caption)
        if year_match:
            before_year = caption[:year_match.start()].strip()
            # Also remove trailing punctuation or separators
            before_year = re.sub(r'[:\-–—|•·]+$', '', before_year).strip()
            if before_year and before_year != caption:
                variants.append(before_year)

        # 4. If the caption is very long, take a substring up to a reasonable length
        #    (sometimes the title is at the very beginning)
        if len(caption) > 80:
            short = caption[:80].rsplit(' ', 1)[0]  # cut at word boundary
            if short and short != caption:
                variants.append(short)

        # Remove duplicates while preserving order
        seen = set()
        unique_variants = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                unique_variants.append(v)
        return unique_variants

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
            title: Search title.
            year: Optional year filter (used where supported).

        Returns:
            Optional[Dict[str, Any]]: Formatted metadata or None if no results.

        Raises:
            Provider-specific exceptions (caught by caller).
        """
        raw_response = None
        formatted = None

        if provider_type == "tmdb_movie":
            raw_response = self.tmdb_client.search_movie(title, year=year)
            results = raw_response.get("results", [])
            if results:
                first = results[0]
                formatted = self.format_tmdb_fn(first, content_type="movie")
            else:
                logger.debug(f"No TMDb movie results for '{title}'")
                return None

        elif provider_type == "tmdb_tv":
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
            return formatted
        else:
            logger.warning(f"Provider {provider_type} returned incomplete data for '{title}'")
            return None

    def _fetch_and_cache(
        self,
        extracted: ExtractedContent,
        content_type: ContentType,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch metadata using the configured provider fallback chain.

        Tries each provider in order, stops at first success, caches the result.

        Args:
            extracted: Extracted content info.
            content_type: Detected content type (used for logging only).

        Returns:
            Optional[Dict[str, Any]]: Formatted metadata or None.
        """
        title = extracted.title
        year = extracted.year

        if not title:
            logger.warning("Cannot fetch: missing title")
            return None

        logger.info(f"Attempting to fetch '{title}' (detected as {content_type.value}) "
                    f"using chain: {self.PROVIDER_CHAIN}")

        for provider in self.PROVIDER_CHAIN:
            try:
                logger.debug(f"Trying provider: {provider}")
                metadata = self._search_and_format(provider, title, year)
                if metadata:
                    logger.info(f"Success with provider {provider} for '{title}'")
                    try:
                        self.save_metadata_fn(metadata)
                    except Exception as e:
                        logger.exception(f"Failed to cache metadata from {provider}: {e}")
                    return metadata
            except (TMDbError, TVMazeError, JikanError, AniListError) as e:
                logger.warning(f"Provider {provider} failed for '{title}': {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error from {provider} for '{title}': {e}")
                continue

        logger.warning(f"No provider could find metadata for '{title}'")
        return None

    def process_caption(self, caption: str) -> Optional[Dict[str, Any]]:
        """
        Main entry point: process a Telegram caption and return metadata.

        Args:
            caption: The raw caption text.

        Returns:
            Optional[Dict[str, Any]]: The metadata in the common schema, or None if not found.
        """
        logger.info(f"Processing caption: {caption[:100]}...")

        # Step 1: Try extraction on multiple caption variants
        variants = self._get_caption_variants(caption)
        extracted = None
        for idx, variant in enumerate(variants):
            try:
                candidate = self.extractor_fn(variant)
                if isinstance(candidate, dict):
                    title = candidate.get("title")
                else:
                    title = candidate.title
                if title:
                    extracted = candidate
                    logger.debug(f"Extraction succeeded with variant #{idx}: {variant[:50]}...")
                    break
            except Exception as e:
                logger.debug(f"Extraction failed for variant #{idx}: {e}")
                continue

        if isinstance(extracted, dict):
            title = extracted.get("title")
        else:
            title = extracted.title
            
        if not extracted or not title:
            logger.warning("No title extracted from any caption variant")
            return None

        # Step 2: Detect content type (used for logging and hinting)
        try:
            content_type = self.detector_fn(extracted)
            logger.info(f"Detected content type: {content_type.value}")
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return None

        # Step 3: Check cache by title and year (if available)
        try:
            cached = self.find_by_title_fn(
                title=title,
                # title=extracted.title,
                content_type=content_type.value if content_type != ContentType.UNKNOWN else None,
                year=extracted.year,
            )
            if cached:
                logger.info(f"Cache hit for title '{title}'")
                return cached
            else:
                logger.info(f"Cache miss for title '{extracted.title}'")
        except Exception as e:
            logger.warning(f"Cache lookup by title failed: {e}, proceeding with fetch")

        # Step 4: Fetch from providers using the fallback chain
        metadata = self._fetch_and_cache(extracted, content_type)

        if metadata:
            logger.info(f"Successfully retrieved metadata for '{extracted.title}'")
            return metadata
        else:
            logger.warning(f"No metadata found for '{title}' after all attempts")
            # logger.warning(f"No metadata found for '{extracted.title}' after all attempts")
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

    # Example caption
    caption = "🔥 Pushpa 2 (2024) 1080p WEB-DL Hindi + Telugu"

    # Create manager
    manager = get_manager()

    # Process
    result = manager.process_caption(caption)

    if result:
        print("Result:", result)
    else:
        print("No metadata found.")
        
        