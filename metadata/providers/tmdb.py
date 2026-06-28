"""
TMDb API v3 client for movie and TV show searches.

This module provides a reusable client for interacting with The Movie Database (TMDb) API.
It includes retry logic, proper error handling, and integrates with Django settings.
"""

import logging
import time
from typing import Optional, Dict, Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.conf import settings

# Module logger
logger = logging.getLogger(__name__)


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
    """

    BASE_URL = "https://api.themoviedb.org/3/"
    DEFAULT_TIMEOUT = 10  # seconds
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 1  # seconds

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """
        Initialize the TMDb client.

        Args:
            api_key: TMDb API key. If None, read from Django settings.
            timeout: Request timeout in seconds. Defaults to DEFAULT_TIMEOUT.
            max_retries: Maximum number of retries for failed requests. Defaults to MAX_RETRIES.

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
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update({"Accept": "application/json"})

        return session

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a GET request to the TMDb API with retry and error handling.

        Args:
            endpoint: API endpoint (e.g., "search/movie").
            params: Query parameters (will be merged with api_key).

        Returns:
            Dict[str, Any]: JSON response from the API.

        Raises:
            TMDbAuthError: On 401 Unauthorized.
            TMDbNotFound: On 404 Not Found.
            TMDbRateLimitError: On 429 Too Many Requests.
            TMDbError: On other HTTP errors or connection issues.
        """
        url = urljoin(self.base_url, endpoint)
        request_params = {"api_key": self.api_key}
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

    # ------------------- Public Methods -------------------

    def search_movie(
        self,
        title: str,
        year: Optional[int] = None,
        include_adult: bool = False,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for movies by title.

        Args:
            title: The movie title to search for.
            year: Optional year to narrow results.
            include_adult: Whether to include adult content.
            region: ISO 3166-1 country code to filter results.

        Returns:
            Dict[str, Any]: The raw TMDb API response.

        Raises:
            TMDbError: For any API error.
        """
        params = {"query": title, "include_adult": str(include_adult).lower()}
        if year:
            params["year"] = year
        if region:
            params["region"] = region

        return self._request("search/movie", params)

    def search_tv(
        self,
        title: str,
        first_air_date_year: Optional[int] = None,
        include_adult: bool = False,
    ) -> Dict[str, Any]:
        """
        Search for TV series by title.

        Args:
            title: The TV series title to search for.
            first_air_date_year: Optional first air year to narrow results.
            include_adult: Whether to include adult content.

        Returns:
            Dict[str, Any]: The raw TMDb API response.

        Raises:
            TMDbError: For any API error.
        """
        params = {"query": title, "include_adult": str(include_adult).lower()}
        if first_air_date_year:
            params["first_air_date_year"] = first_air_date_year

        return self._request("search/tv", params)

    def get_movie(self, movie_id: int, append_to_response: Optional[str] = None) -> Dict[str, Any]:
        """
        Get detailed information about a movie by its TMDb ID.

        Args:
            movie_id: The TMDb movie ID.
            append_to_response: Comma-separated list of additional endpoints to include.

        Returns:
            Dict[str, Any]: The raw TMDb API response.

        Raises:
            TMDbNotFound: If the movie does not exist.
            TMDbError: For any other API error.
        """
        params = {}
        if append_to_response:
            params["append_to_response"] = append_to_response

        return self._request(f"movie/{movie_id}", params)

    def get_tv(self, tv_id: int, append_to_response: Optional[str] = None) -> Dict[str, Any]:
        """
        Get detailed information about a TV series by its TMDb ID.

        Args:
            tv_id: The TMDb TV series ID.
            append_to_response: Comma-separated list of additional endpoints to include.

        Returns:
            Dict[str, Any]: The raw TMDb API response.

        Raises:
            TMDbNotFound: If the TV series does not exist.
            TMDbError: For any other API error.
        """
        params = {}
        if append_to_response:
            params["append_to_response"] = append_to_response

        return self._request(f"tv/{tv_id}", params)


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
    # Simple test (requires Django settings configured or direct API key)
    import sys

    # Configure logging to see output
    logging.basicConfig(level=logging.DEBUG)

    # Attempt to get client
    try:
        client = TMDbClient(api_key="your_api_key_here")  # Replace with actual key for testing
        result = client.search_movie("Inception", year=2010)
        print(result)
    except TMDbError as e:
        print(f"Error: {e}", file=sys.stderr)