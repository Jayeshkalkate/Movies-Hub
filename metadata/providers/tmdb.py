# tmdb.py
"""
TMDb API v3 client for movie and TV show searches.

This module provides a reusable client for interacting with The Movie Database (TMDb) API.
It includes retry logic, proper error handling, and integrates with Django settings.
It also integrates the movie_parser to clean raw captions before searching.

Usage:
    from tmdb import get_tmdb_client
    client = get_tmdb_client()

    # For clean titles:
    result = client.search_movie("Inception", year=2010)

    # For raw captions / filenames (recommended):
    result = client.search_movie_from_text("Inception 2010 1080p WEB-DL x264")

    # To get the first (best) match directly:
    movie = client.get_best_movie_from_text("The Matrix 1999 BluRay")
    if movie:
        print(movie['title'], movie['release_date'])
"""

import logging
import re
import time
from typing import Optional, Dict, Any, List, Union, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.conf import settings

# Try to import the movie parser
try:
    from coremovieshub.utils.movie_parser import parse_movie
    PARSER_AVAILABLE = True
except ImportError:
    PARSER_AVAILABLE = False

    def parse_movie(text: str) -> Dict[str, Any]:
        """
        Fallback parser when movie_parser is unavailable.

        Cleans common tags, extracts year, and returns a dict.
        """
        # Remove common release tags
        cleaned = re.sub(
            r'\b(?:WEB-DL|WEBRip|BluRay|HDRip|x264|x265|HEVC|DDP|AAC|AC3|DTS|HDTV|DVD|BDrip)\b',
            '',
            text,
            flags=re.I
        )
        # Remove file extensions
        cleaned = re.sub(r'\.[a-zA-Z0-9]{2,4}$', '', cleaned)
        # Replace dots/underscores with spaces
        cleaned = re.sub(r'[._]', ' ', cleaned)
        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', cleaned)
        year = int(year_match.group()) if year_match else None
        if year:
            cleaned = re.sub(r'\b(19|20)\d{2}\b', '', cleaned)
        # Clean up extra spaces and title
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return {
            "title": cleaned,
            "year": year,
            "season": None,
            "episode": None,
            "quality": None,
            "languages": [],
        }

# Module logger
logger = logging.getLogger(__name__)

__all__ = [
    "TMDbClient",
    "TMDbError",
    "TMDbAuthError",
    "TMDbNotFound",
    "TMDbRateLimitError",
    "get_tmdb_client",
]


# ------------------- Custom Exceptions -------------------

class TMDbError(Exception):
    """Base exception for TMDb API errors."""
    pass


class TMDbAuthError(TMDbError):
    """Raised when API key is invalid or missing."""
    pass


class TMDbNotFound(TMDbError):
    """Raised when the requested resource is not found."""
    pass


class TMDbRateLimitError(TMDbError):
    """Raised when rate limit is exceeded."""
    pass


# ------------------- Client Class -------------------

class TMDbClient:
    """
    A client for interacting with the TMDb API v3.

    Reads the API key from Django settings (TMDB_API_KEY) if not provided.
    Uses a requests Session with retries and timeout.

    Attributes:
        api_key (str): The TMDb API key.
        base_url (str): Base URL for the TMDb API.
        session (requests.Session): The session used for all requests.
        timeout (int): Request timeout in seconds.
        max_retries (int): Maximum number of retries.
    """

    BASE_URL = "https://api.themoviedb.org/3/"
    DEFAULT_TIMEOUT = 10  # seconds
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 1  # seconds
    DEFAULT_LANGUAGE = "en-US"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        language: Optional[str] = None,
    ):
        """
        Initialize the TMDb client.

        Args:
            api_key: TMDb API key. If None, read from Django settings.
            timeout: Request timeout in seconds. Defaults to DEFAULT_TIMEOUT.
            max_retries: Maximum number of retries for failed requests. Defaults to MAX_RETRIES.
            language: Default language for responses (ISO 639-1 code). Defaults to "en-US".

        Raises:
            TMDbAuthError: If no API key is provided and none is found in settings.
        """
        if api_key is None:
            try:
                api_key = settings.TMDB_API_KEY
            except AttributeError:
                raise TMDbAuthError(
                    "TMDB_API_KEY not found in Django settings. "
                    "Please set it in your settings file."
                )

        if not api_key:
            raise TMDbAuthError("TMDb API key is empty or not configured.")

        self.api_key = api_key
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.max_retries = max_retries or self.MAX_RETRIES
        self.language = language or self.DEFAULT_LANGUAGE
        self.base_url = self.BASE_URL

        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """
        Create a requests Session with retry logic.

        Returns:
            requests.Session: Configured session.
        """
        session = requests.Session()

        # Set up retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.RETRY_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,  # We handle status ourselves
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update({"Accept": "application/json"})

        return session

    def close(self) -> None:
        """Close the underlying requests session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a GET request to the TMDb API with retry and error handling.

        Args:
            endpoint: API endpoint (e.g., "search/movie").
            params: Query parameters (will be merged with api_key and language).

        Returns:
            Dict[str, Any]: JSON response from the API.

        Raises:
            TMDbAuthError: On 401 Unauthorized.
            TMDbNotFound: On 404 Not Found.
            TMDbRateLimitError: On 429 Too Many Requests.
            TMDbError: On other HTTP errors or connection issues.
        """
        url = self.base_url.rstrip('/') + '/' + endpoint.lstrip('/')
        request_params = {
            "api_key": self.api_key,
            "language": self.language,
        }
        if params:
            request_params.update(params)

        try:
            logger.debug(f"TMDb request: GET {url} with params {request_params}")
            response = self.session.get(
                url,
                params=request_params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None

            if status_code == 401:
                logger.error("TMDb authentication error (invalid API key).")
                raise TMDbAuthError("Invalid or missing TMDb API key.") from e
            elif status_code == 404:
                logger.info(f"TMDb resource not found: {url}")
                raise TMDbNotFound(f"Resource not found: {endpoint}") from e
            elif status_code == 429:
                logger.warning("TMDb rate limit exceeded.")
                raise TMDbRateLimitError("Rate limit exceeded. Please try again later.") from e
            else:
                logger.error(f"TMDb HTTP error {status_code}: {e}")
                raise TMDbError(f"HTTP error {status_code}: {e.response.text}") from e

        except requests.exceptions.ConnectionError as e:
            logger.error(f"TMDb connection error: {e}")
            raise TMDbError("Connection error while communicating with TMDb.") from e

        except requests.exceptions.Timeout as e:
            logger.error(f"TMDb request timed out: {e}")
            raise TMDbError("Request timed out.") from e

        except requests.exceptions.RequestException as e:
            logger.error(f"TMDb request failed: {e}")
            raise TMDbError(f"Request failed: {e}") from e

    # ------------------- Public Search Methods -------------------

    def search_movie(
        self,
        title: str,
        year: Optional[int] = None,
        include_adult: bool = False,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for movies by a clean title.

        **Note:** If you have raw text (e.g., from a filename or caption), use
        `search_movie_from_text()` instead, which automatically parses and cleans
        the input for better results.

        Args:
            title: The movie title (should be clean, without extra metadata).
            year: Optional year to narrow results.
            include_adult: Whether to include adult content.
            region: ISO 3166-1 country code to filter results.

        Returns:
            Dict[str, Any]: The raw TMDb API response (contains 'results' list).

        Raises:
            TMDbError: For any API error.
        """
        params: Dict[str, Any] = {
            "query": title,
            "include_adult": str(include_adult).lower(),
        }
        if year:
            params["year"] = year
        if region:
            params["region"] = region

        logger.info(f"Searching TMDb for movie: title='{title}', year={year}, region={region}")
        response = self._request("search/movie", params)
        total = response.get("total_results", 0)
        logger.info(f"TMDb movie search returned {total} results")
        # Verify and log the first result for debugging
        if total > 0:
            first = response["results"][0]
            logger.debug(f"Top result: {first.get('title')} ({first.get('release_date', 'N/A')}) [ID: {first.get('id')}]")
        return response

    def search_movie_from_text(
        self,
        raw_text: str,
        include_adult: bool = False,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parse a raw caption/filename to extract a clean title and year,
        then search TMDb for the movie.

        This is the preferred method when you have raw Telegram captions or filenames.

        Args:
            raw_text: The raw text (caption, filename) containing movie info.
            include_adult: Whether to include adult content.
            region: ISO 3166-1 country code to filter results.

        Returns:
            Dict[str, Any]: The raw TMDb API response (contains 'results' list).

        Raises:
            TMDbError: For any API error.
        """
        if not raw_text:
            raise TMDbError("Empty text provided for parsing.")

        parsed = parse_movie(raw_text)
        title = parsed.get("title")
        year = parsed.get("year")

        if not title:
            logger.warning("Could not extract title from text, using raw text.")
            title = raw_text.strip()
            # Attempt to extract year via regex as fallback
            year_match = re.search(r'\b(19|20)\d{2}\b', raw_text)
            if year_match:
                year = int(year_match.group())

        logger.info(f"Parsed from raw text: title='{title}', year={year} (raw: {raw_text[:50]}...)")
        return self.search_movie(title, year, include_adult, region)

    def search_tv(
        self,
        title: str,
        first_air_date_year: Optional[int] = None,
        include_adult: bool = False,
    ) -> Dict[str, Any]:
        """
        Search for TV series by a clean title.

        **Note:** If you have raw text, use `search_tv_from_text()`.

        Args:
            title: The TV series title (should be clean).
            first_air_date_year: Optional first air year to narrow results.
            include_adult: Whether to include adult content.

        Returns:
            Dict[str, Any]: The raw TMDb API response (contains 'results' list).

        Raises:
            TMDbError: For any API error.
        """
        params: Dict[str, Any] = {
            "query": title,
            "include_adult": str(include_adult).lower(),
        }
        if first_air_date_year:
            params["first_air_date_year"] = first_air_date_year

        logger.info(f"Searching TMDb for TV: title='{title}', first_air_date_year={first_air_date_year}")
        response = self._request("search/tv", params)
        total = response.get("total_results", 0)
        logger.info(f"TMDb TV search returned {total} results")
        if total > 0:
            first = response["results"][0]
            logger.debug(f"Top result: {first.get('name')} ({first.get('first_air_date', 'N/A')}) [ID: {first.get('id')}]")
        return response

    def search_tv_from_text(
        self,
        raw_text: str,
        include_adult: bool = False,
    ) -> Dict[str, Any]:
        """
        Parse a raw caption/filename to extract a clean title and year,
        then search TMDb for a TV series.

        Args:
            raw_text: The raw text (caption, filename) containing TV info.
            include_adult: Whether to include adult content.

        Returns:
            Dict[str, Any]: The raw TMDb API response (contains 'results' list).

        Raises:
            TMDbError: For any API error.
        """
        if not raw_text:
            raise TMDbError("Empty text provided for parsing.")

        parsed = parse_movie(raw_text)
        title = parsed.get("title")
        year = parsed.get("year")  # for TV, this is first_air_date_year

        if not title:
            logger.warning("Could not extract title from text, using raw text.")
            title = raw_text.strip()
            year_match = re.search(r'\b(19|20)\d{2}\b', raw_text)
            if year_match:
                year = int(year_match.group())

        logger.info(f"Parsed from raw text for TV: title='{title}', year={year} (raw: {raw_text[:50]}...)")
        return self.search_tv(title, year, include_adult)

    def search_movie_auto(
        self,
        text: str,
        include_adult: bool = False,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Automatically decide whether to parse the text or treat it as a clean title.

        If the text contains common release tags (e.g., WEB-DL, BluRay, x264) or
        looks like a filename, it will be parsed. Otherwise, it will be used as-is.

        This is a convenience method that combines both approaches.

        Args:
            text: The input text (could be clean title or raw caption/filename).
            include_adult: Whether to include adult content.
            region: ISO 3166-1 country code to filter results.

        Returns:
            Dict[str, Any]: The raw TMDb API response.

        Raises:
            TMDbError: For any API error.
        """
        # Heuristic: if it contains common release tags or multiple dots/underscores,
        # it's likely a filename/caption.
        raw_patterns = [
            r'\b(?:WEB-DL|WEBRip|BluRay|HDRip|x264|x265|HEVC|DDP|AAC|AC3|DTS|HDTV|DVD|BDrip)\b',
            r'[\._\-]\s*(?:19|20)\d{2}\s*[\._\-]',  # year with separators
            r'\bS\d{1,2}E\d{1,2}\b',  # season/episode
        ]
        is_raw = any(re.search(pattern, text, re.I) for pattern in raw_patterns)

        if is_raw:
            logger.debug(f"Auto-detected raw text, using search_movie_from_text: {text}")
            return self.search_movie_from_text(text, include_adult, region)
        else:
            logger.debug(f"Auto-detected clean title, using search_movie: {text}")
            return self.search_movie(text, None, include_adult, region)

    def search_tv_auto(
        self,
        text: str,
        include_adult: bool = False,
    ) -> Dict[str, Any]:
        """
        Automatically decide whether to parse the text or treat it as a clean title
        for TV series searches.

        Args:
            text: The input text.
            include_adult: Whether to include adult content.

        Returns:
            Dict[str, Any]: The raw TMDb API response.

        Raises:
            TMDbError: For any API error.
        """
        raw_patterns = [
            r'\b(?:WEB-DL|WEBRip|BluRay|HDRip|x264|x265|HEVC|DDP|AAC|AC3|DTS|HDTV|DVD|BDrip)\b',
            r'[\._\-]\s*(?:19|20)\d{2}\s*[\._\-]',
            r'\bS\d{1,2}E\d{1,2}\b',
        ]
        is_raw = any(re.search(pattern, text, re.I) for pattern in raw_patterns)

        if is_raw:
            logger.debug(f"Auto-detected raw text, using search_tv_from_text: {text}")
            return self.search_tv_from_text(text, include_adult)
        else:
            logger.debug(f"Auto-detected clean title, using search_tv: {text}")
            return self.search_tv(text, None, include_adult)

    # ------------------- "Get Best Match" Methods -------------------

    def get_best_movie(
        self,
        title: str,
        year: Optional[int] = None,
        include_adult: bool = False,
        region: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Search for a movie and return the first (best) result, or None if none found.

        This is a convenience wrapper around `search_movie()`.

        Args:
            title: Clean movie title.
            year: Optional year.
            include_adult: Whether to include adult content.
            region: ISO 3166-1 country code.

        Returns:
            Optional[Dict[str, Any]]: The first movie result, or None.
        """
        data = self.search_movie(title, year, include_adult, region)
        results = data.get("results", [])
        if results:
            logger.info(f"Best movie match: {results[0].get('title')} ({results[0].get('release_date', 'N/A')})")
            # Verify result integrity
            self._verify_movie_result(results[0])
            return results[0]
        else:
            logger.warning(f"No movie results found for title='{title}', year={year}")
            return None

    def get_best_movie_from_text(
        self,
        raw_text: str,
        include_adult: bool = False,
        region: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Parse raw text and return the first (best) movie result.

        Args:
            raw_text: Raw caption/filename.
            include_adult: Whether to include adult content.
            region: ISO 3166-1 country code.

        Returns:
            Optional[Dict[str, Any]]: The first movie result, or None.
        """
        data = self.search_movie_from_text(raw_text, include_adult, region)
        results = data.get("results", [])
        if results:
            logger.info(f"Best movie match from text: {results[0].get('title')} ({results[0].get('release_date', 'N/A')})")
            self._verify_movie_result(results[0])
            return results[0]
        else:
            logger.warning(f"No movie results found for raw text: {raw_text[:50]}...")
            return None

    def get_best_tv(
        self,
        title: str,
        first_air_date_year: Optional[int] = None,
        include_adult: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Search for a TV series and return the first (best) result.

        Args:
            title: Clean TV series title.
            first_air_date_year: Optional first air year.
            include_adult: Whether to include adult content.

        Returns:
            Optional[Dict[str, Any]]: The first TV result, or None.
        """
        data = self.search_tv(title, first_air_date_year, include_adult)
        results = data.get("results", [])
        if results:
            logger.info(f"Best TV match: {results[0].get('name')} ({results[0].get('first_air_date', 'N/A')})")
            self._verify_tv_result(results[0])
            return results[0]
        else:
            logger.warning(f"No TV results found for title='{title}', year={first_air_date_year}")
            return None

    def get_best_tv_from_text(
        self,
        raw_text: str,
        include_adult: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Parse raw text and return the first (best) TV series result.

        Args:
            raw_text: Raw caption/filename.
            include_adult: Whether to include adult content.

        Returns:
            Optional[Dict[str, Any]]: The first TV result, or None.
        """
        data = self.search_tv_from_text(raw_text, include_adult)
        results = data.get("results", [])
        if results:
            logger.info(f"Best TV match from text: {results[0].get('name')} ({results[0].get('first_air_date', 'N/A')})")
            self._verify_tv_result(results[0])
            return results[0]
        else:
            logger.warning(f"No TV results found for raw text: {raw_text[:50]}...")
            return None

    # ------------------- Verification Helpers -------------------

    def _verify_movie_result(self, movie: Dict[str, Any]) -> None:
        """
        Verify that a movie result has the minimum required fields and log warnings if missing.

        Args:
            movie: A movie result dict from TMDb.
        """
        required = ["id", "title"]
        for field in required:
            if field not in movie:
                logger.warning(f"Movie result missing field '{field}': {movie.get('id', 'unknown')}")
        if not movie.get("release_date"):
            logger.debug(f"Movie has no release_date: {movie.get('title')}")
        if not movie.get("poster_path"):
            logger.debug(f"Movie has no poster_path: {movie.get('title')}")
        # Check that the title is not empty
        if not movie.get("title"):
            logger.warning(f"Movie result has empty title: {movie}")

    def _verify_tv_result(self, tv: Dict[str, Any]) -> None:
        """
        Verify that a TV result has the minimum required fields and log warnings if missing.

        Args:
            tv: A TV series result dict from TMDb.
        """
        required = ["id", "name"]
        for field in required:
            if field not in tv:
                logger.warning(f"TV result missing field '{field}': {tv.get('id', 'unknown')}")
        if not tv.get("first_air_date"):
            logger.debug(f"TV has no first_air_date: {tv.get('name')}")
        if not tv.get("poster_path"):
            logger.debug(f"TV has no poster_path: {tv.get('name')}")
        if not tv.get("name"):
            logger.warning(f"TV result has empty name: {tv}")

    # ------------------- Detail Methods -------------------

    def get_movie(
        self,
        movie_id: int,
        append_to_response: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get detailed information about a movie by its TMDb ID.

        Args:
            movie_id: The TMDb movie ID.
            append_to_response: Comma-separated list of additional endpoints to include.
            language: Override the default language for this request.

        Returns:
            Dict[str, Any]: The movie details.

        Raises:
            TMDbNotFound: If the movie does not exist.
            TMDbError: For any other API error.
        """
        params: Dict[str, Any] = {}
        if append_to_response:
            params["append_to_response"] = append_to_response
        if language:
            params["language"] = language

        logger.debug(f"Fetching movie details for ID {movie_id}")
        response = self._request(f"movie/{movie_id}", params)
        # Verify the response has basic fields
        if response:
            self._verify_movie_result(response)
        return response

    def get_tv(
        self,
        tv_id: int,
        append_to_response: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get detailed information about a TV series by its TMDb ID.

        Args:
            tv_id: The TMDb TV series ID.
            append_to_response: Comma-separated list of additional endpoints to include.
            language: Override the default language.

        Returns:
            Dict[str, Any]: The TV series details.

        Raises:
            TMDbNotFound: If the TV series does not exist.
            TMDbError: For any other API error.
        """
        params: Dict[str, Any] = {}
        if append_to_response:
            params["append_to_response"] = append_to_response
        if language:
            params["language"] = language

        logger.debug(f"Fetching TV details for ID {tv_id}")
        response = self._request(f"tv/{tv_id}", params)
        if response:
            self._verify_tv_result(response)
        return response

    def get_movie_by_imdb_id(self, imdb_id: str) -> Dict[str, Any]:
        """
        Find a movie by its IMDb ID (e.g., "tt1375666").

        This uses the TMDb 'find' endpoint.

        Args:
            imdb_id: The IMDb ID (with 'tt' prefix).

        Returns:
            Dict[str, Any]: The movie details, or raises TMDbNotFound if not found.

        Raises:
            TMDbNotFound: If no movie with that IMDb ID is found.
            TMDbError: For any other API error.
        """
        params = {"external_source": "imdb_id"}
        data = self._request(f"find/{imdb_id}", params)
        results = data.get("movie_results", [])
        if not results:
            raise TMDbNotFound(f"No movie found for IMDb ID: {imdb_id}")
        # Return the first result (usually the best match)
        movie = results[0]
        self._verify_movie_result(movie)
        return movie

    def get_tv_by_imdb_id(self, imdb_id: str) -> Dict[str, Any]:
        """
        Find a TV series by its IMDb ID (e.g., "tt0903747").

        Args:
            imdb_id: The IMDb ID (with 'tt' prefix).

        Returns:
            Dict[str, Any]: The TV series details.

        Raises:
            TMDbNotFound: If no TV series with that IMDb ID is found.
            TMDbError: For any other API error.
        """
        params = {"external_source": "imdb_id"}
        data = self._request(f"find/{imdb_id}", params)
        results = data.get("tv_results", [])
        if not results:
            raise TMDbNotFound(f"No TV series found for IMDb ID: {imdb_id}")
        tv = results[0]
        self._verify_tv_result(tv)
        return tv

    # ------------------- Additional Endpoints -------------------

    def get_movie_credits(self, movie_id: int) -> Dict[str, Any]:
        """Get the cast and crew credits for a movie."""
        return self._request(f"movie/{movie_id}/credits")

    def get_tv_credits(self, tv_id: int) -> Dict[str, Any]:
        """Get the cast and crew credits for a TV series."""
        return self._request(f"tv/{tv_id}/credits")

    def get_movie_images(self, movie_id: int) -> Dict[str, Any]:
        """Get the posters, backdrops, etc. for a movie."""
        return self._request(f"movie/{movie_id}/images")

    def get_tv_images(self, tv_id: int) -> Dict[str, Any]:
        """Get the posters, backdrops, etc. for a TV series."""
        return self._request(f"tv/{tv_id}/images")

    def get_movie_videos(self, movie_id: int) -> Dict[str, Any]:
        """Get the trailers and other videos for a movie."""
        return self._request(f"movie/{movie_id}/videos")

    def get_tv_videos(self, tv_id: int) -> Dict[str, Any]:
        """Get the trailers and other videos for a TV series."""
        return self._request(f"tv/{tv_id}/videos")

    # ------------------- Image URL Helper -------------------

    def get_image_url(self, path: str, size: str = "w500") -> str:
        """
        Build a full image URL from a path.

        Args:
            path: The relative image path (e.g., "/abc123.jpg").
            size: The image size (e.g., "w500", "original").

        Returns:
            str: The full image URL.
        """
        if not path:
            return ""
        return f"https://image.tmdb.org/t/p/{size}{path}"


# ------------------- Helper to get client instance -------------------

def get_tmdb_client() -> TMDbClient:
    """
    Factory function to get a TMDbClient instance with settings from Django.

    Returns:
        TMDbClient: Configured client.

    Raises:
        TMDbAuthError: If API key is missing.
    """
    return TMDbClient()


# ------------------- Example usage (for testing) -------------------

if __name__ == "__main__":
    import sys

    # Configure logging to see output
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Attempt to get client (requires API key in environment or settings)
    try:
        # For testing, you can pass api_key directly:
        # client = TMDbClient(api_key="your_api_key_here")
        client = get_tmdb_client()  # reads from Django settings

        # Test with raw caption
        raw = "Paatal Lok 2020 S01 AMZN WEB DL"
        print("Testing search_movie_from_text...")
        result = client.search_movie_from_text(raw)
        print(f"Found {result.get('total_results', 0)} results.")
        best = client.get_best_movie_from_text(raw)
        if best:
            print(f"Best match: {best['title']} ({best.get('release_date', 'N/A')})")

        # Test TV search
        raw_tv = "The Expanse S01E05 1080p"
        best_tv = client.get_best_tv_from_text(raw_tv)
        if best_tv:
            print(f"Best TV match: {best_tv['name']} ({best_tv.get('first_air_date', 'N/A')})")

    except TMDbError as e:
        print(f"TMDb error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
    finally:
        if 'client' in locals():
            client.close()
            
