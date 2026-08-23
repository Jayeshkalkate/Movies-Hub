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
         - If cached and fresh (within expiry), return metadata.
         - If cached but stale, treat as miss and re-fetch.
    4. Else, query providers based on content type:
         - Movie: TMDB Movie only (stop on first success)
         - Not Movie: TMDB Movie → TMDB TV → TVMaze → AniList → Jikan
           (stop on first success)
    5. Format the raw response into the common schema.
    6. Save to cache (upsert by telegram_file_id if provided).
    7. Return the metadata.

All external dependencies are injected via constructor for testability.
"""

import asyncio
import logging
import re
import traceback
from typing import Optional, Dict, Any, Callable, List

from .cache import (
    save_metadata,
    find_by_title,
    find_by_external_id,
    find_by_telegram_file_id,
)
from .extractor import extract, ExtractedContent
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

    Provider ordering:
        - If content_type == MOVIE: try TMDB Movie only.
        - Otherwise: try TMDB Movie → TMDB TV → TVMaze → AniList → Jikan.

    All synchronous I/O is executed in a thread pool to avoid blocking the
    async event loop.
    """

    def __init__(
        self,
        tmdb_client: Optional[TMDbClient] = None,
        tvmaze_client: Optional[TVMazeClient] = None,
        jikan_client: Optional[JikanClient] = None,
        anilist_client: Optional[AniListClient] = None,
        find_by_title_fn: Callable = find_by_title,
        find_by_external_id_fn: Optional[Callable] = find_by_external_id,  # fixed default
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
            logger.info("=" * 60)
            logger.info("TMDB SEARCH (Movie) | title=%s | year=%s", title, year)
            raw_details = self.tmdb_client.get_best_movie(
                title=title,
                year=year,
                include_adult=False,
                region=None,
                formatted=False,      # get raw details
            )
            if raw_details:
                logger.info("TMDB DETAILS (Movie) | id=%s | title=%s", raw_details.get("id"), raw_details.get("title"))
                formatted = self.format_tmdb_fn(raw_details, content_type="movie")
            else:
                logger.debug(f"SEARCH: No TMDb movie results for '{title}'")
                return None

        elif provider_type == "tmdb_tv":
            logger.info("=" * 60)
            logger.info("TMDB SEARCH (TV) | title=%s | year=%s", title, year)
            raw_details = self.tmdb_client.get_best_tv(
                title=title,
                first_air_date_year=year,
                include_adult=False,
                formatted=False,
            )
            if raw_details:
                logger.info("TMDB DETAILS (TV) | id=%s | title=%s", raw_details.get("id"), raw_details.get("name"))
                formatted = self.format_tmdb_fn(raw_details, content_type="tv")
            else:
                logger.debug(f"SEARCH: No TMDb TV results for '{title}'")
                return None

        elif provider_type == "tvmaze":
            logger.info("=" * 60)
            logger.info("TVMAZE SEARCH | title=%s", title)
            raw_response = self.tvmaze_client.search_show(title)
            if raw_response:
                first = raw_response[0]
                logger.info("TVMAZE DETAILS | id=%s | title=%s", first.get("id"), first.get("name"))
                formatted = self.format_tvmaze_fn(first)
            else:
                logger.debug(f"SEARCH: No TVMaze results for '{title}'")
                return None

        elif provider_type == "anilist":
            logger.info("=" * 60)
            logger.info("ANILIST SEARCH | title=%s | year=%s", title, year)
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
                logger.info("ANILIST DETAILS | id=%s | title=%s", first.get("id"), first.get("title", {}).get("romaji"))
                formatted = self.format_anilist_fn(first)
            else:
                logger.debug(f"SEARCH: No AniList results for '{title}'")
                return None

        elif provider_type == "jikan":
            logger.info("=" * 60)
            logger.info("JIKAN SEARCH | title=%s | year=%s", title, year)
            raw_response = self.jikan_client.search_anime(title, year=year)
            results = raw_response.get("data", [])
            if results:
                first = results[0]
                logger.info("JIKAN DETAILS | mal_id=%s | title=%s", first.get("mal_id"), first.get("title"))
                formatted = self.format_jikan_fn(first)
            else:
                logger.debug(f"SEARCH: No Jikan results for '{title}'")
                return None

        else:
            raise ValueError(f"Unknown provider_type: {provider_type}")

        # Ensure we have a valid result with an external ID
        if formatted and formatted.get("external_id"):
            formatted["_provider"] = provider_type
            logger.info("FORMATTER | provider=%s | external_id=%s", provider_type, formatted["external_id"])
            return formatted
        else:
            logger.warning(f"RESULT: Provider {provider_type} returned incomplete data for '{title}'")
            return None

    # ---------- Helper: clean and validate metadata ----------
    def _clean_metadata(self, metadata: Dict[str, Any], extracted: ExtractedContent) -> Dict[str, Any]:
        """
        Normalize, validate, and set defaults for critical fields.
        """
        # Normalize title
        if "title" in metadata:
            metadata["title"] = (metadata["title"] or "").strip()

        # Ensure required fields exist with defaults
        metadata.setdefault("poster", "")
        metadata.setdefault("backdrop", "")
        metadata.setdefault("overview", "")
        metadata.setdefault("runtime", None)
        metadata.setdefault("genres", [])
        metadata.setdefault("vote_average", None)
        metadata.setdefault("release_date", None)

        # Clean overview: remove HTML and excessive whitespace
        if metadata.get("overview"):
            overview = metadata["overview"]
            overview = re.sub(r"<[^>]+>", "", overview)   # strip HTML tags
            overview = re.sub(r"\s+", " ", overview).strip()
            metadata["overview"] = overview

        # Fallback overview to extracted title if empty
        if not metadata.get("overview") and extracted.title:
            metadata["overview"] = extracted.title

        # Normalize runtime: ensure it's a positive integer
        runtime = metadata.get("runtime")
        try:
            runtime = int(runtime)
            if runtime <= 0:
                runtime = None
        except (TypeError, ValueError):
            runtime = None
        metadata["runtime"] = runtime

        # Validate poster/backdrop URLs
        for field in ("poster", "backdrop"):
            url = metadata.get(field)
            if url and not str(url).startswith(("http://", "https://")):
                logger.warning("Invalid %s URL: %s", field, url)
                metadata[field] = ""

        # Validate release_date: must be at least 4 characters (YYYY)
        release = metadata.get("release_date")
        if release and len(str(release)) < 4:
            metadata["release_date"] = None

        return metadata

    # ---------- Synchronous core processing ----------
    def _sync_process(
        self,
        caption: str,
        filename: Optional[str] = None,
        telegram_file_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Synchronous implementation of the metadata pipeline.
        This is run inside a thread to avoid blocking the async loop.
        """
        # ---- UPLOAD START ----
        logger.info("=" * 60)
        logger.info("UPLOAD START")
        if filename:
            search_text = f"{filename} {caption}".strip()
            logger.info("RAW (filename + caption): %s", search_text[:200])
        else:
            search_text = caption
            logger.info("RAW (caption): %s", search_text[:200])
        logger.info("=" * 60)

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
            logger.warning("STAGE: PARSED -> No title extracted from any text variant")
            logger.info("UPLOAD COMPLETE (failure)")
            logger.info("=" * 60)
            return None

        # ---- STAGE: PARSED ----
        logger.info("TITLE: %s", extracted.title)
        logger.info("YEAR: %s", extracted.year)
        logger.info("SEASON: %s", extracted.season)
        logger.info("EPISODE: %s", extracted.episode)
        logger.info("QUALITY: %s", extracted.quality)
        logger.info("LANGUAGES: %s", extracted.languages)

        # Step 2: Enhance with language detection from the full search_text
        if not extracted.languages:
            langs = detect_languages(search_text)
            if langs:
                extracted.languages = langs
                logger.debug(f"Detected languages from text: {langs}")

        # Step 3: Detect content type (will also parse episode/season and subtype)
        try:
            content_type = self.detector_fn(extracted)
            extracted.content_type = content_type
            logger.info("TYPE: %s", content_type.value)
            if hasattr(extracted, 'subtype') and extracted.subtype:
                logger.info("SUBTYPE: %s", extracted.subtype)
        except Exception:
            logger.exception("STAGE: DETECTED -> Detection failed, falling back to UNKNOWN")
            content_type = ContentType.UNKNOWN
            extracted.content_type = content_type
            logger.info("TYPE: %s", content_type.value)

        # Step 4: Check cache
        cache_hit = False
        # Try by telegram_file_id first if provided
        if telegram_file_id and self.find_by_external_id_fn:
            try:
                cached = self.find_by_external_id_fn(telegram_file_id, "tmdb")
                if cached:
                    logger.info("CACHE HIT (by telegram_file_id): %s", telegram_file_id)
                    cache_hit = True
                    logger.info("UPLOAD COMPLETE (cached)")
                    logger.info("=" * 60)
                    return cached
            except Exception as e:
                logger.warning(f"STAGE: CACHE -> Lookup by telegram_file_id failed: {e}")

        # Then by title/year/type
        if not cache_hit:
            try:
                cached = self.find_by_title_fn(
                    title=extracted.title,
                    content_type=content_type.value if content_type != ContentType.UNKNOWN else None,
                    year=extracted.year,
                )
                if cached:
                    logger.info("CACHE HIT (by title/year/type): %s (%s)", extracted.title, extracted.year)
                    cache_hit = True
                    logger.info("UPLOAD COMPLETE (cached)")
                    logger.info("=" * 60)
                    return cached
                else:
                    logger.info("CACHE MISS (not found or stale): %s", extracted.title)
            except Exception as e:
                logger.warning(f"STAGE: CACHE -> Lookup by title failed: {e}, proceeding with fetch")

        # Step 5: Fetch from providers (sequential, stop on success)
        # ---- Fetch and cache ----
        title = extracted.title
        year = extracted.year

        # Normalize title for provider searches
        search_title = clean_text(title)
        if not search_title:
            logger.warning(f"Title became empty after normalization, using original '{title}'")
            search_title = title
        else:
            logger.debug(f"Normalized title for search: '{search_title}' (original: '{title}')")

        # Provider selection
        if content_type == ContentType.MOVIE:
            providers = ["tmdb_movie"]
        else:
            providers = ["tmdb_movie", "tmdb_tv", "tvmaze", "anilist", "jikan"]

        logger.info(
            f"SEARCH: Fetching '{title}' (detected as {content_type.value}) "
            f"trying providers in order: {', '.join(providers)}"
        )

        for provider in providers:
            try:
                result = self._search_and_format(provider, search_title, year)
                if result:
                    # Clean and validate the metadata before caching
                    result = self._clean_metadata(result, extracted)
                    result["_provider"] = provider

                    logger.info(
                        "RESULT: Matched %s | %s (%s) | poster=%s backdrop=%s runtime=%s overview=%d chars",
                        provider,
                        result.get("title"),
                        result.get("external_id"),
                        bool(result.get("poster")),
                        bool(result.get("backdrop")),
                        result.get("runtime"),
                        len(result.get("overview") or ""),
                    )

                    # Cache it (upsert by telegram_file_id if provided)
                    try:
                        logger.info("SAVE: Caching metadata id=%s title=%s", result.get("external_id"), result.get("title"))
                        self.save_metadata_fn(result, telegram_file_id=telegram_file_id)
                        logger.info("SAVE: Metadata cached successfully.")
                    except Exception as e:
                        logger.exception(f"CACHE: Failed to cache metadata: {e}")

                    logger.info("UPLOAD COMPLETE (success)")
                    logger.info("=" * 60)
                    return result
                else:
                    logger.debug(f"SEARCH: Provider {provider} returned no result for '{search_title}'")
            except Exception as e:
                logger.warning(f"SEARCH: Provider {provider} failed for '{search_title}': {e}")
                logger.debug(traceback.format_exc())
                continue

        # If we reach here, no provider succeeded
        logger.warning(f"SEARCH: No provider returned data for '{search_title}'")
        logger.info("UPLOAD COMPLETE (failure)")
        logger.info("=" * 60)
        return None

    # ---------- Async entry point ----------
    async def process_caption(
        self,
        caption: str,
        filename: Optional[str] = None,
        telegram_file_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Main entry point (async): process a Telegram caption (and optional filename)
        and return metadata.

        All blocking I/O is offloaded to a thread pool via asyncio.to_thread.

        Args:
            caption: The raw caption text.
            filename: Optional filename (e.g., from a torrent or file name)
                      to improve extraction.
            telegram_file_id: Optional unique ID from Telegram for cache upsert.

        Returns:
            Optional[Dict[str, Any]]: The metadata in the common schema,
                                      or None if not found.
        """
        # Run the synchronous processing in a thread to avoid blocking the event loop.
        return await asyncio.to_thread(
            self._sync_process,
            caption,
            filename,
            telegram_file_id,
        )


# ------------------- Convenience function -------------------
def get_manager() -> Manager:
    """
    Factory function to get a Manager instance with default dependencies.

    Returns:
        Manager: Configured manager.
    """
    return Manager()


# ------------------- Example usage (sync) -------------------
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Example caption and filename
    caption = "🔥 Pushpa 2 (2024) 1080p WEB-DL Hindi + Telugu"
    filename = "Pushpa.2.The.Rule.2024.1080p.mkv"

    # Create manager
    manager = get_manager()

    # For testing, we can call the sync method directly (or run async)
    # Using async is recommended in production.
    import asyncio
    result = asyncio.run(manager.process_caption(caption, filename=filename))

    if result:
        print("Result:", result)
    else:
        print("No metadata found.")
