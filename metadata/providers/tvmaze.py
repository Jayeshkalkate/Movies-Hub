"""
TVMaze API client for searching and retrieving TV show information.

This module provides a reusable client for the TVMaze REST API (https://www.tvmaze.com/api).
It includes retry logic, error handling, and integrates with Django settings.

TVMaze does not require an API key for public endpoints.
"""

import logging
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Optional Django integration
try:
    from django.conf import settings
except ImportError:
    settings = None

# Module logger
logger = logging.getLogger(__name__)


# ------------------- Custom Exceptions -------------------

class TVMazeError(Exception):
    """Base exception for TVMaze API errors."""
    pass


class TVMazeNotFound(TVMazeError):
    """Raised when the requested show is not found."""
    pass


class TVMazeRateLimitError(TVMazeError):
    """Raised when rate limit is exceeded."""
    pass


# ------------------- Client Class -------------------

class TVMazeClient:
    """
    A client for interacting with the TVMaze API.

    Attributes:
        base_url (str): Base URL for the TVMaze API.
        session (requests.Session): The session used for all requests.
        timeout (int): Request timeout in seconds.
    """

    BASE_URL = "https://api.tvmaze.com/"
    DEFAULT_TIMEOUT = 10  # seconds
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 1  # seconds

    def __init__(
        self,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """
        Initialize the TVMaze client.

        Args:
            timeout: Request timeout in seconds. Defaults to DEFAULT_TIMEOUT.
            max_retries: Maximum number of retries for failed requests. Defaults to MAX_RETRIES.
        """
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

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Send a GET request to the TVMaze API with retry and error handling.

        Args:
            endpoint: API endpoint (e.g., "search/shows").
            params: Query parameters.

        Returns:
            The JSON response (could be list or dict) from the API.

        Raises:
            TVMazeNotFound: On 404 Not Found.
            TVMazeRateLimitError: On 429 Too Many Requests.
            TVMazeError: On other HTTP errors or connection issues.
        """
        url = urljoin(self.base_url, endpoint)

        try:
            logger.debug(f"TVMaze request: GET {url} with params {params}")
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()

            # If response is empty, return None
            if not response.content:
                return None

            return response.json()

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None

            if status_code == 404:
                logger.info(f"TVMaze resource not found: {url}")
                raise TVMazeNotFound(f"Resource not found: {endpoint}") from e
            elif status_code == 429:
                logger.warning("TVMaze rate limit exceeded.")
                raise TVMazeRateLimitError("Rate limit exceeded. Please try again later.") from e
            else:
                logger.error(f"TVMaze HTTP error {status_code}: {e}")
                raise TVMazeError(f"HTTP error {status_code}: {e.response.text}") from e

        except requests.exceptions.ConnectionError as e:
            logger.error(f"TVMaze connection error: {e}")
            raise TVMazeError("Connection error while communicating with TVMaze.") from e

        except requests.exceptions.Timeout as e:
            logger.error(f"TVMaze request timed out: {e}")
            raise TVMazeError("Request timed out.") from e

        except requests.exceptions.RequestException as e:
            logger.error(f"TVMaze request failed: {e}")
            raise TVMazeError(f"Request failed: {e}") from e

    # ------------------- Public Methods -------------------

    def search_show(self, title: str) -> List[Dict[str, Any]]:
        """
        Search for TV shows by title.

        Args:
            title: The show title to search for.

        Returns:
            List[Dict[str, Any]]: List of show objects with embedded show details.
            Each item contains a 'show' key with the show information.

        Raises:
            TVMazeError: For any API error.
        """
        params = {"q": title}
        result = self._request("search/shows", params)
        # The result is a list of objects with a 'show' key
        return result if result is not None else []

    def get_show(self, show_id: int, embed: Optional[str] = None) -> Dict[str, Any]:
        """
        Get detailed information about a show by its TVMaze ID.

        Args:
            show_id: The TVMaze show ID.
            embed: Optional embed parameter (e.g., "cast", "episodes", "seasons").

        Returns:
            Dict[str, Any]: The raw TVMaze API response.

        Raises:
            TVMazeNotFound: If the show does not exist.
            TVMazeError: For any other API error.
        """
        params = {}
        if embed:
            params["embed"] = embed

        return self._request(f"shows/{show_id}", params)


# ------------------- Helper to get client instance -------------------

def get_tvmaze_client() -> TVMazeClient:
    """
    Factory function to get a TVMazeClient instance.

    Returns:
        TVMazeClient: Configured client.
    """
    return TVMazeClient()


# ------------------- Example usage (for testing) -------------------

if __name__ == "__main__":
    # Simple test
    import sys

    logging.basicConfig(level=logging.DEBUG)

    client = TVMazeClient()
    try:
        # Search for Breaking Bad
        results = client.search_show("Breaking Bad")
        print(f"Found {len(results)} results.")
        if results:
            show = results[0]["show"]
            print(f"Top result: {show['name']} (ID: {show['id']})")

            # Get full show details
            show_details = client.get_show(show["id"], embed="cast")
            print(f"Show details: {show_details.get('name')}")
            print(f"Number of episodes: {show_details.get('_embedded', {}).get('episodes', [])}")
    except TVMazeError as e:
        print(f"Error: {e}", file=sys.stderr)