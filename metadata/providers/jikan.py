# jikan.py
"""
Jikan API client for searching and retrieving anime information.

This module provides a client for the Jikan REST API (unofficial MyAnimeList API).
It uses requests with retry logic, error handling, and logging.

Jikan API does not require an API key.
API documentation: https://jikan.moe/
Base URL: https://api.jikan.moe/v4/
"""

import logging
from typing import Optional, Dict, Any, List, Union
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Module logger
logger = logging.getLogger(__name__)

__all__ = [
    "JikanClient",
    "JikanError",
    "JikanNotFound",
    "JikanRateLimitError",
    "get_jikan_client",
]


# ------------------- Custom Exceptions -------------------

class JikanError(Exception):
    """Base exception for Jikan API errors."""
    pass


class JikanNotFound(JikanError):
    """Raised when the requested resource is not found."""
    pass


class JikanRateLimitError(JikanError):
    """Raised when rate limit is exceeded."""
    pass


# ------------------- Client Class -------------------

class JikanClient:
    """
    A client for interacting with the Jikan API v4.

    Attributes:
        base_url (str): Base URL for the Jikan API.
        session (requests.Session): The session used for all requests.
        timeout (int): Request timeout in seconds.
        max_retries (int): Maximum number of retries.
    """

    BASE_URL = "https://api.jikan.moe/v4/"
    DEFAULT_TIMEOUT = 10  # seconds
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 1  # seconds

    def __init__(
        self,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """
        Initialize the Jikan client.

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
            raise_on_status=False,  # We handle status ourselves
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update({"Accept": "application/json"})

        return session

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a GET request to the Jikan API with retry and error handling.

        Args:
            endpoint: API endpoint (e.g., "anime").
            params: Query parameters.

        Returns:
            Dict[str, Any]: The JSON response from the API.

        Raises:
            JikanNotFound: On 404 Not Found.
            JikanRateLimitError: On 429 Too Many Requests.
            JikanError: On other HTTP errors or connection issues.
        """
        url = urljoin(self.base_url, endpoint)

        try:
            logger.debug(f"Jikan request: GET {url} with params {params}")
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None

            if status_code == 404:
                logger.info(f"Jikan resource not found: {url}")
                raise JikanNotFound(f"Resource not found: {endpoint}") from e
            elif status_code == 429:
                logger.warning("Jikan rate limit exceeded.")
                raise JikanRateLimitError("Rate limit exceeded. Please try again later.") from e
            else:
                logger.error(f"Jikan HTTP error {status_code}: {e}")
                raise JikanError(f"HTTP error {status_code}: {e.response.text if e.response else ''}") from e

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Jikan connection error: {e}")
            raise JikanError("Connection error while communicating with Jikan.") from e

        except requests.exceptions.Timeout as e:
            logger.error(f"Jikan request timed out: {e}")
            raise JikanError("Request timed out.") from e

        except requests.exceptions.RequestException as e:
            logger.error(f"Jikan request failed: {e}")
            raise JikanError(f"Request failed: {e}") from e

    # ------------------- Public Methods -------------------

    def search_anime(
        self,
        title: str,
        page: int = 1,
        limit: int = 25,
        genre: Optional[int] = None,
        status: Optional[str] = None,
        rating: Optional[str] = None,
        score: Optional[float] = None,
        season: Optional[str] = None,
        year: Optional[int] = None,
        order_by: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for anime by title with optional filters.

        Args:
            title: The anime title to search for.
            page: Page number.
            limit: Number of results per page (max 25).
            genre: Genre ID to filter by.
            status: Filter by status (airing, complete, upcoming).
            rating: Filter by rating (g, pg, pg13, r17, r, rx).
            score: Minimum score (0-10).
            season: Filter by season (winter, spring, summer, fall).
            year: Filter by year.
            order_by: Order by field (e.g., title, score, rank, popularity).
            sort: Sort order (asc, desc).

        Returns:
            Dict[str, Any]: The raw Jikan API response.

        Raises:
            JikanError: For any API error.
        """
        params: Dict[str, Any] = {
            "q": title,
            "page": page,
            "limit": min(limit, 25)  # Jikan max limit is 25
        }
        if genre is not None:
            params["genres"] = genre
        if status:
            params["status"] = status
        if rating:
            params["rating"] = rating
        if score is not None:
            params["score"] = score
        if season:
            params["season"] = season
        if year:
            params["year"] = year
        if order_by:
            params["order_by"] = order_by
        if sort:
            params["sort"] = sort

        return self._request("anime", params)

    def get_anime(self, anime_id: int) -> Dict[str, Any]:
        """
        Get detailed information about an anime by its MyAnimeList ID.

        Args:
            anime_id: The MyAnimeList anime ID.

        Returns:
            Dict[str, Any]: The raw Jikan API response.

        Raises:
            JikanNotFound: If the anime does not exist.
            JikanError: For any other API error.
        """
        return self._request(f"anime/{anime_id}")

    def get_anime_episodes(self, anime_id: int, page: Optional[int] = 1) -> Dict[str, Any]:
        """
        Get episode list for an anime by its MyAnimeList ID.

        Args:
            anime_id: The MyAnimeList anime ID.
            page: Page number.

        Returns:
            Dict[str, Any]: The raw Jikan API response.

        Raises:
            JikanNotFound: If the anime does not exist.
            JikanError: For any other API error.
        """
        params = {"page": page} if page else {}
        return self._request(f"anime/{anime_id}/episodes", params)

    def close(self) -> None:
        """Close the underlying session."""
        self.session.close()


# ------------------- Helper to get client instance -------------------

def get_jikan_client() -> JikanClient:
    """
    Factory function to get a JikanClient instance.

    Returns:
        JikanClient: Configured client.
    """
    return JikanClient()


# ------------------- Example usage (for testing) -------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    client = get_jikan_client()
    try:
        # Search for Naruto
        results = client.search_anime("Naruto")
        total = results.get("pagination", {}).get("items", {}).get("total", 0)
        print(f"Found {total} results.")
        if results.get("data"):
            first = results["data"][0]
            print(f"Top result: {first['title']} (ID: {first['mal_id']})")

            # Get anime details
            anime = client.get_anime(first["mal_id"])
            synopsis = anime.get("synopsis", "N/A")
            print(f"Synopsis: {synopsis[:200]}...")
    except JikanError as e:
        print(f"Error: {e}", file=sys.stderr)
    finally:
        client.close()
        
        
