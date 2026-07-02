# tmdb.py
"""
TMDb API v3 client for movie and TV show searches.

This module provides a reusable client for interacting with The Movie Database (TMDb) API.
It includes retry logic, proper error handling, and integrates with Django settings.
It also integrates the movie_parser to clean raw captions before searching.

Usage:
    from tmdb import get_tmdb_client
    client = get_tmdb_client()

    # For clean titles (returns formatted dict):
    movie = client.get_best_movie("Inception", year=2010)
    print(movie['title'], movie['release_year'], movie['overview'])

    # For raw captions / filenames:
    movie = client.get_best_movie_from_text("Inception 2010 1080p WEB-DL x264")

    # To get raw details (not formatted) if needed:
    raw = client.get_best_movie("The Matrix", formatted=False)
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


# ------------------- Formatter Functions -------------------

def format_movie(details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format raw movie details from TMDb into a clean, structured dict.

    Args:
        details: The full movie details response from TMDb.

    Returns:
        Dict with keys: id, title, original_title, release_year, release_date,
                         overview, poster_path, backdrop_path, vote_average,
                         vote_count, genres, runtime, status, tagline, imdb_id,
                         original_language, budget, revenue,
                         production_companies, production_countries,
                         spoken_languages.
    """
    def get_year(date_str):
        if date_str and len(date_str) >= 4:
            return date_str[:4]
        return None

    return {
        "id": details.get("id"),
        "title": details.get("title"),
        "original_title": details.get("original_title"),
        "release_year": get_year(details.get("release_date")),
        "release_date": details.get("release_date"),
        "overview": details.get("overview"),
        "poster_path": details.get("poster_path"),
        "backdrop_path": details.get("backdrop_path"),
        "vote_average": details.get("vote_average"),
        "vote_count": details.get("vote_count"),
        "genres": [g["name"] for g in details.get("genres", [])],
        "runtime": details.get("runtime"),
        "status": details.get("status"),
        "tagline": details.get("tagline"),
        "imdb_id": details.get("imdb_id"),
        "original_language": details.get("original_language"),
        # --- New fields ---
        "budget": details.get("budget"),
        "revenue": details.get("revenue"),
        "production_companies": [c["name"] for c in details.get("production_companies", [])],
        "production_countries": [c["name"] for c in details.get("production_countries", [])],
        "spoken_languages": [l["name"] for l in details.get("spoken_languages", [])],
    }


def format_tv(details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format raw TV series details from TMDb into a clean, structured dict.

    Args:
        details: The full TV series details response from TMDb.

    Returns:
        Dict with keys: id, name, original_name, first_air_year, first_air_date,
                         last_air_date, overview, poster_path, backdrop_path,
                         vote_average, vote_count, genres, number_of_seasons,
                         number_of_episodes, status, tagline, imdb_id.
    """
    def get_year(date_str):
        if date_str and len(date_str) >= 4:
            return date_str[:4]
        return None

    return {
        "id": details.get("id"),
        "name": details.get("name"),
        "original_name": details.get("original_name"),
        "first_air_year": get_year(details.get("first_air_date")),
        "first_air_date": details.get("first_air_date"),
        "last_air_date": details.get("last_air_date"),
        "overview": details.get("overview"),
        "poster_path": details.get("poster_path"),
        "backdrop_path": details.get("backdrop_path"),
        "vote_average": details.get("vote_average"),
        "vote_count": details.get("vote_count"),
        "genres": [g["name"] for g in details.get("genres", [])],
        "number_of_seasons": details.get("number_of_seasons"),
        "number_of_episodes": details.get("number_of_episodes"),
        "status": details.get("status"),
        "tagline": details.get("tagline"),
        "imdb_id": details.get("external_ids", {}).get("imdb_id"),
        "original_language": details.get("original_language"),
    }


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

        **Important:** The returned results are raw search results. For full details,
        use `get_best_movie()` which will fetch and format the details.

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

        **Important:** The returned results are raw search results. For full details,
        use `get_best_movie_from_text()`.

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

        **Important:** The returned results are raw search results. For full details,
        use `get_best_tv()`.

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

        **Important:** The returned results are raw search results. For full details,
        use `get_best_tv_from_text()`.

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

        **Important:** The returned results are raw search results. For full details,
        use `get_best_movie()` or `get_best_movie_from_text()` directly.

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

        **Important:** The returned results are raw search results. For full details,
        use `get_best_tv()` or `get_best_tv_from_text()`.

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

    # ------------------- "Get Best Match" Methods (with Details & Formatting) -------------------

    def get_best_movie(
        self,
        title: str,
        year: Optional[int] = None,
        include_adult: bool = False,
        region: Optional[str] = None,
        formatted: bool = True,
    ) -> Optional[Union[Dict[str, Any], None]]:
        """
        Search for a movie, fetch the full details for the best match, and optionally format.

        This method implements the full pipeline: Search → ID → Details → Formatter.

        Args:
            title: Clean movie title.
            year: Optional year.
            include_adult: Whether to include adult content.
            region: ISO 3166-1 country code.
            formatted: If True, return a formatted dict (via format_movie).
                       If False, return the raw details from the details endpoint.

        Returns:
            Optional[Union[Dict[str, Any], None]]: The best match (formatted or raw details),
            or None if no match found.

        Raises:
            TMDbError: If the details fetch fails (e.g., network error).
        """
        # Step 1: Search
        data = self.search_movie(title, year, include_adult, region)
        results = data.get("results", [])
        if not results:
            logger.warning(f"No movie results found for title='{title}', year={year}")
            return None

        best_search = results[0]
        movie_id = best_search.get("id")
        if not movie_id:
            logger.warning(f"Search result missing ID for title='{title}'")
            return None

        # Step 2: Fetch details using the ID
        try:
            details = self.get_movie(movie_id)
        except TMDbError as e:
            logger.error(f"Failed to fetch details for movie ID {movie_id}: {e}")
            # Re-raise or return None? We'll raise to signal failure.
            raise

        # Step 3: Format if requested
        if formatted:
            return format_movie(details)
        else:
            return details

    def get_best_movie_from_text(
        self,
        raw_text: str,
        include_adult: bool = False,
        region: Optional[str] = None,
        formatted: bool = True,
    ) -> Optional[Union[Dict[str, Any], None]]:
        """
        Parse raw text, search, fetch details, and format the best movie match.

        Implements the full pipeline: Parse → Search → ID → Details → Formatter.

        Args:
            raw_text: Raw caption/filename.
            include_adult: Whether to include adult content.
            region: ISO 3166-1 country code.
            formatted: If True, return formatted dict; else raw details.

        Returns:
            Optional[Union[Dict[str, Any], None]]: The best match (formatted or raw),
            or None if no match.
        """
        # Step 1: Parse text and search
        data = self.search_movie_from_text(raw_text, include_adult, region)
        results = data.get("results", [])
        if not results:
            logger.warning(f"No movie results found for raw text: {raw_text[:50]}...")
            return None

        best_search = results[0]
        movie_id = best_search.get("id")
        if not movie_id:
            logger.warning(f"Search result missing ID for raw text: {raw_text[:50]}...")
            return None

        # Step 2: Fetch details
        try:
            details = self.get_movie(movie_id)
        except TMDbError as e:
            logger.error(f"Failed to fetch details for movie ID {movie_id}: {e}")
            raise

        # Step 3: Format
        if formatted:
            return format_movie(details)
        else:
            return details

    def get_best_tv(
        self,
        title: str,
        first_air_date_year: Optional[int] = None,
        include_adult: bool = False,
        formatted: bool = True,
    ) -> Optional[Union[Dict[str, Any], None]]:
        """
        Search for a TV series, fetch full details, and optionally format.

        Implements: Search → ID → Details → Formatter.

        Args:
            title: Clean TV series title.
            first_air_date_year: Optional first air year.
            include_adult: Whether to include adult content.
            formatted: If True, return formatted dict; else raw details.

        Returns:
            Optional[Union[Dict[str, Any], None]]: The best match, or None.
        """
        data = self.search_tv(title, first_air_date_year, include_adult)
        results = data.get("results", [])
        if not results:
            logger.warning(f"No TV results found for title='{title}', year={first_air_date_year}")
            return None

        best_search = results[0]
        tv_id = best_search.get("id")
        if not tv_id:
            logger.warning(f"Search result missing ID for title='{title}'")
            return None

        try:
            details = self.get_tv(tv_id)
        except TMDbError as e:
            logger.error(f"Failed to fetch details for TV ID {tv_id}: {e}")
            raise

        if formatted:
            return format_tv(details)
        else:
            return details

    def get_best_tv_from_text(
        self,
        raw_text: str,
        include_adult: bool = False,
        formatted: bool = True,
    ) -> Optional[Union[Dict[str, Any], None]]:
        """
        Parse raw text, search for TV, fetch details, and optionally format.

        Implements: Parse → Search → ID → Details → Formatter.

        Args:
            raw_text: Raw caption/filename.
            include_adult: Whether to include adult content.
            formatted: If True, return formatted dict; else raw details.

        Returns:
            Optional[Union[Dict[str, Any], None]]: The best match, or None.
        """
        data = self.search_tv_from_text(raw_text, include_adult)
        results = data.get("results", [])
        if not results:
            logger.warning(f"No TV results found for raw text: {raw_text[:50]}...")
            return None

        best_search = results[0]
        tv_id = best_search.get("id")
        if not tv_id:
            logger.warning(f"Search result missing ID for raw text: {raw_text[:50]}...")
            return None

        try:
            details = self.get_tv(tv_id)
        except TMDbError as e:
            logger.error(f"Failed to fetch details for TV ID {tv_id}: {e}")
            raise

        if formatted:
            return format_tv(details)
        else:
            return details

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
            Dict[str, Any]: The raw movie details.

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
            Dict[str, Any]: The raw TV series details.

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

        This uses the TMDb 'find' endpoint. The result is the raw movie details.

        Args:
            imdb_id: The IMDb ID (with 'tt' prefix).

        Returns:
            Dict[str, Any]: The raw movie details.

        Raises:
            TMDbNotFound: If no movie with that IMDb ID is found.
            TMDbError: For any other API error.
        """
        params = {"external_source": "imdb_id"}
        data = self._request(f"find/{imdb_id}", params)
        results = data.get("movie_results", [])
        if not results:
            raise TMDbNotFound(f"No movie found for IMDb ID: {imdb_id}")
        movie = results[0]
        self._verify_movie_result(movie)
        return movie

    def get_tv_by_imdb_id(self, imdb_id: str) -> Dict[str, Any]:
        """
        Find a TV series by its IMDb ID (e.g., "tt0903747").

        Returns the raw TV details.

        Args:
            imdb_id: The IMDb ID (with 'tt' prefix).

        Returns:
            Dict[str, Any]: The raw TV series details.

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

    # ------------------- Verification Helpers (private) -------------------

    def _verify_movie_result(self, movie: Dict[str, Any]) -> None:
        """Verify that a movie result has the minimum required fields."""
        required = ["id", "title"]
        for field in required:
            if field not in movie:
                logger.warning(f"Movie result missing field '{field}': {movie.get('id', 'unknown')}")
        if not movie.get("title"):
            logger.warning(f"Movie result has empty title: {movie}")

    def _verify_tv_result(self, tv: Dict[str, Any]) -> None:
        """Verify that a TV result has the minimum required fields."""
        required = ["id", "name"]
        for field in required:
            if field not in tv:
                logger.warning(f"TV result missing field '{field}': {tv.get('id', 'unknown')}")
        if not tv.get("name"):
            logger.warning(f"TV result has empty name: {tv}")


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

    try:
        client = get_tmdb_client()

        # Test with raw caption – will fetch details and format
        raw = "Inception 2010 1080p WEB-DL"
        movie = client.get_best_movie_from_text(raw)
        if movie:
            print("Formatted movie:")
            for key, value in movie.items():
                if value is not None:
                    print(f"  {key}: {value}")
        else:
            print("No movie found.")

        # Test TV
        raw_tv = "The Expanse S01E05 1080p"
        tv = client.get_best_tv_from_text(raw_tv)
        if tv:
            print("\nFormatted TV:")
            for key, value in tv.items():
                if value is not None:
                    print(f"  {key}: {value}")

        # To get raw details:
        raw_details = client.get_best_movie("The Matrix", formatted=False)
        if raw_details:
            print("\nRaw details keys:", list(raw_details.keys()))

    except TMDbError as e:
        print(f"TMDb error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
    finally:
        if 'client' in locals():
            client.close()
            
