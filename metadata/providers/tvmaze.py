"""
TVMaze API client for searching and retrieving TV show information.

This module provides a reusable client for the TVMaze REST API (https://www.tvmaze.com/api).
It includes retry logic, error handling, and integrates with Django settings.

TVMaze does not require an API key for public endpoints.
"""

import logging
import time
from typing import Optional, Dict, Any, List, Union, Iterator
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Optional Django integration for settings
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
    """Raised when the requested show, episode, or resource is not found."""
    pass


class TVMazeRateLimitError(TVMazeError):
    """Raised when rate limit is exceeded and retries are exhausted."""
    pass


# ------------------- Client Class -------------------

class TVMazeClient:
    """
    A client for interacting with the TVMaze API.

    Attributes:
        base_url (str): Base URL for the TVMaze API.
        session (requests.Session): The session used for all requests.
        timeout (int): Request timeout in seconds.
        max_retries (int): Maximum number of retries on failure.
        retry_backoff_factor (float): Backoff factor for retries.
    """

    BASE_URL = "https://api.tvmaze.com/"
    DEFAULT_TIMEOUT = 30  # seconds
    MAX_RETRIES = 5
    RETRY_BACKOFF_FACTOR = 0.5  # seconds, exponential backoff
    RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]

    def __init__(
        self,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff_factor: Optional[float] = None,
    ):
        """
        Initialize the TVMaze client.

        Args:
            timeout: Request timeout in seconds. Defaults to DEFAULT_TIMEOUT.
            max_retries: Maximum number of retries for failed requests. Defaults to MAX_RETRIES.
            retry_backoff_factor: Backoff factor for retries. Defaults to RETRY_BACKOFF_FACTOR.
        """
        # Allow override from Django settings if available
        if settings:
            self.timeout = getattr(settings, "TVMAZE_TIMEOUT", timeout or self.DEFAULT_TIMEOUT)
            self.max_retries = getattr(settings, "TVMAZE_MAX_RETRIES", max_retries or self.MAX_RETRIES)
            self.retry_backoff_factor = getattr(settings, "TVMAZE_RETRY_BACKOFF_FACTOR",
                                                retry_backoff_factor or self.RETRY_BACKOFF_FACTOR)
        else:
            self.timeout = timeout or self.DEFAULT_TIMEOUT
            self.max_retries = max_retries or self.MAX_RETRIES
            self.retry_backoff_factor = retry_backoff_factor or self.RETRY_BACKOFF_FACTOR

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
            backoff_factor=self.retry_backoff_factor,
            status_forcelist=self.RETRY_STATUS_FORCELIST,
            allowed_methods=["GET"],
            raise_on_status=False,  # We handle status manually for better control
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update({
            "Accept": "application/json",
            "User-Agent": "TVMaze Python Client",
        })

        return session

    def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        retry_on_429: bool = True,
    ) -> Any:
        """
        Send a GET request to the TVMaze API with retry and error handling.

        Args:
            endpoint: API endpoint (e.g., "search/shows").
            params: Query parameters.
            retry_on_429: If True, will sleep and retry on 429 status.

        Returns:
            The JSON response (could be list or dict) from the API.

        Raises:
            TVMazeNotFound: On 404 Not Found.
            TVMazeRateLimitError: On 429 Too Many Requests and no retry.
            TVMazeError: On other HTTP errors or connection issues.
        """
        url = urljoin(self.base_url, endpoint)
        attempt = 0

        while True:
            attempt += 1
            try:
                logger.debug(f"TVMaze request: GET {url} with params {params}")
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                )

                # Handle 429 rate limiting
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    if retry_on_429 and attempt <= self.max_retries:
                        sleep_time = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                        logger.warning(f"Rate limited by TVMaze. Sleeping {sleep_time}s and retrying (attempt {attempt}/{self.max_retries})...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        raise TVMazeRateLimitError("Rate limit exceeded. Please try again later.")

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
                    # This shouldn't happen if we handled above, but just in case
                    if retry_on_429 and attempt <= self.max_retries:
                        sleep_time = 2 ** attempt
                        logger.warning(f"Rate limited (HTTPError). Sleeping {sleep_time}s and retrying...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        raise TVMazeRateLimitError("Rate limit exceeded.") from e
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

            break  # Success, exit loop

    # ------------------- Public Methods -------------------

    def search_show(self, title: str) -> List[Dict[str, Any]]:
        """
        Search for TV shows by title.

        Args:
            title: The show title to search for.

        Returns:
            List[Dict[str, Any]]: List of search results, each containing a 'show' key
            with the show information and a 'score' key.

        Raises:
            TVMazeError: For any API error.
        """
        params = {"q": title}
        result = self._request("search/shows", params)
        return result if isinstance(result, list) else []

    def get_show(self, show_id: int, embed: Optional[Union[str, List[str]]] = None) -> Dict[str, Any]:
        """
        Get detailed information about a show by its TVMaze ID.

        Args:
            show_id: The TVMaze show ID.
            embed: Optional embed parameter (e.g., "cast", "episodes", "seasons").
                   Can be a string or a list of strings.

        Returns:
            Dict[str, Any]: The raw TVMaze API response.

        Raises:
            TVMazeNotFound: If the show does not exist.
            TVMazeError: For any other API error.
        """
        params = {}
        if embed:
            if isinstance(embed, list):
                embed = ",".join(embed)
            params["embed"] = embed

        return self._request(f"shows/{show_id}", params)

    def get_show_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """
        Get the first matching show by title using the search endpoint.

        Args:
            title: The show title.

        Returns:
            Optional[Dict[str, Any]]: The show object if found, else None.
        """
        results = self.search_show(title)
        if results:
            return results[0].get("show")
        return None

    def get_show_episodes(
        self,
        show_id: int,
        season: Optional[int] = None,
        embed: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get episodes for a given show, optionally filtered by season.

        Args:
            show_id: The TVMaze show ID.
            season: Optional season number to filter.
            embed: Optional embed parameter (e.g., "guestcast", "crew").

        Returns:
            List[Dict[str, Any]]: List of episode objects.

        Raises:
            TVMazeNotFound: If the show does not exist.
            TVMazeError: For any API error.
        """
        params = {}
        if embed:
            if isinstance(embed, list):
                embed = ",".join(embed)
            params["embed"] = embed

        endpoint = f"shows/{show_id}/episodes"
        if season is not None:
            params["specials"] = 0  # TVMaze uses ?specials=1 to include specials, but season filtering is done via the 'season' parameter? Actually, the endpoint is /episodes?season=1.
            # Actually TVMaze supports filtering by season via query parameter? The documentation says: /shows/{id}/episodes?season=1
            params["season"] = season

        result = self._request(endpoint, params)
        return result if isinstance(result, list) else []

    def get_show_seasons(self, show_id: int) -> List[Dict[str, Any]]:
        """
        Get all seasons for a given show.

        Args:
            show_id: The TVMaze show ID.

        Returns:
            List[Dict[str, Any]]: List of season objects.

        Raises:
            TVMazeNotFound: If the show does not exist.
            TVMazeError: For any API error.
        """
        result = self._request(f"shows/{show_id}/seasons")
        return result if isinstance(result, list) else []

    def get_episode(self, episode_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific episode by its TVMaze ID.

        Args:
            episode_id: The TVMaze episode ID.

        Returns:
            Dict[str, Any]: The episode object.

        Raises:
            TVMazeNotFound: If the episode does not exist.
            TVMazeError: For any API error.
        """
        return self._request(f"episodes/{episode_id}")

    def get_show_cast(self, show_id: int) -> List[Dict[str, Any]]:
        """
        Get the cast of a show.

        Args:
            show_id: The TVMaze show ID.

        Returns:
            List[Dict[str, Any]]: List of cast members with character and actor info.

        Raises:
            TVMazeNotFound: If the show does not exist.
        """
        result = self._request(f"shows/{show_id}/cast")
        return result if isinstance(result, list) else []

    def get_show_crew(self, show_id: int) -> List[Dict[str, Any]]:
        """
        Get the crew of a show.

        Args:
            show_id: The TVMaze show ID.

        Returns:
            List[Dict[str, Any]]: List of crew members with type and person info.

        Raises:
            TVMazeNotFound: If the show does not exist.
        """
        result = self._request(f"shows/{show_id}/crew")
        return result if isinstance(result, list) else []

    def get_schedule(
        self,
        country: Optional[str] = None,
        date: Optional[str] = None,  # YYYY-MM-DD
        embed: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get the full TV schedule for a given date or country.

        Args:
            country: Optional country code (e.g., "US", "GB").
            date: Optional date in YYYY-MM-DD format (defaults to today).
            embed: Optional embed parameter (e.g., "show").

        Returns:
            List[Dict[str, Any]]: List of schedule items (each has an "airdate", "show", etc.).

        Raises:
            TVMazeError: For any API error.
        """
        params = {}
        if country:
            params["country"] = country
        if date:
            params["date"] = date
        if embed:
            if isinstance(embed, list):
                embed = ",".join(embed)
            params["embed"] = embed

        result = self._request("schedule", params)
        return result if isinstance(result, list) else []

    def get_show_akas(self, show_id: int) -> List[Dict[str, Any]]:
        """
        Get all alternate names (AKAs) for a show.

        Args:
            show_id: The TVMaze show ID.

        Returns:
            List[Dict[str, Any]]: List of AKA objects with name, country, etc.
        """
        result = self._request(f"shows/{show_id}/akas")
        return result if isinstance(result, list) else []

    def close(self):
        """Close the underlying requests session."""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


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
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    with TVMazeClient() as client:
        try:
            # Search for Breaking Bad
            results = client.search_show("Breaking Bad")
            print(f"Found {len(results)} results.")
            if results:
                show = results[0]["show"]
                print(f"Top result: {show['name']} (ID: {show['id']})")

                # Get full show details with cast and episodes embedded
                show_details = client.get_show(show["id"], embed=["cast", "episodes"])
                print(f"Show details: {show_details.get('name')}")
                embedded = show_details.get("_embedded", {})
                cast_count = len(embedded.get("cast", []))
                episodes_count = len(embedded.get("episodes", []))
                print(f"Cast count: {cast_count}, Episodes count: {episodes_count}")

                # Get seasons
                seasons = client.get_show_seasons(show["id"])
                print(f"Number of seasons: {len(seasons)}")

                # Get episodes for season 1
                episodes = client.get_show_episodes(show["id"], season=1)
                print(f"Episodes in season 1: {len(episodes)}")

                # Get schedule for today
                schedule = client.get_schedule(country="US")
                print(f"Number of shows airing today in US: {len(schedule)}")
        except TVMazeError as e:
            print(f"Error: {e}", file=sys.stderr)
            
