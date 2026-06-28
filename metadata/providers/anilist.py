"""
AniList GraphQL API client for searching and retrieving anime information.

This module provides a client for the AniList GraphQL API (https://anilist.co).
It uses requests with retry logic, error handling, logging, and session reuse.
All requests are sent as POST with JSON payload containing the GraphQL query and variables.

API documentation: https://anilist.gitbook.io/anilist-apiv2-docs/
Base URL: https://graphql.anilist.co
"""

import logging
from typing import Optional, Dict, Any, List
import json

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Module logger
logger = logging.getLogger(__name__)


# ------------------- Custom Exceptions -------------------

class AniListError(Exception):
    """Base exception for AniList API errors."""
    pass


class AniListNotFound(AniListError):
    """Raised when the requested resource is not found."""
    pass


class AniListRateLimitError(AniListError):
    """Raised when rate limit is exceeded."""
    pass


# ------------------- GraphQL Queries -------------------

# Query for searching anime by title with pagination and filters
SEARCH_ANIME_QUERY = """
query ($search: String, $page: Int, $perPage: Int, $genre: String, $year: Int, $status: MediaStatus, $format: MediaFormat, $sort: [MediaSort]) {
  Page(page: $page, perPage: $perPage) {
    pageInfo {
      total
      currentPage
      lastPage
      hasNextPage
      perPage
    }
    media(search: $search, genre: $genre, seasonYear: $year, status: $status, format: $format, sort: $sort, type: ANIME) {
      id
      idMal
      title {
        romaji
        english
        native
      }
      description
      startDate {
        year
        month
        day
      }
      endDate {
        year
        month
        day
      }
      episodes
      duration
      status
      format
      genres
      averageScore
      popularity
      season
      seasonYear
      coverImage {
        large
        medium
      }
      bannerImage
      synonyms
      countryOfOrigin
      source
      isAdult
      rankings {
        rank
        type
        year
        context
      }
      studios {
        nodes {
          name
        }
      }
      nextAiringEpisode {
        episode
        timeUntilAiring
      }
    }
  }
}
"""

# Query for getting detailed anime by ID
GET_ANIME_QUERY = """
query ($id: Int) {
  Media(id: $id, type: ANIME) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    description
    startDate {
      year
      month
      day
    }
    endDate {
      year
      month
      day
    }
    episodes
    duration
    status
    format
    genres
    averageScore
    popularity
    season
    seasonYear
    coverImage {
      large
      medium
    }
    bannerImage
    synonyms
    countryOfOrigin
    source
    isAdult
    hashtag
    trailer {
      id
      site
      thumbnail
    }
    rankings {
      rank
      type
      year
      context
    }
    studios {
      nodes {
        name
      }
    }
    staff {
      edges {
        node {
          name {
            full
          }
        }
        role
      }
    }
    characters {
      edges {
        node {
          name {
            full
          }
          image {
            large
          }
        }
        role
      }
    }
    relations {
      edges {
        relationType
        node {
          id
          title {
            romaji
            english
          }
          type
          format
        }
      }
    }
    recommendations {
      nodes {
        mediaRecommendation {
          id
          title {
            romaji
            english
          }
        }
      }
    }
    nextAiringEpisode {
      episode
      timeUntilAiring
    }
  }
}
"""


# ------------------- Client Class -------------------

class AniListClient:
    """
    A client for interacting with the AniList GraphQL API.

    Attributes:
        base_url (str): Base URL for the GraphQL endpoint.
        session (requests.Session): The session used for all requests.
        timeout (int): Request timeout in seconds.
        max_retries (int): Maximum number of retries on failure.
    """

    BASE_URL = "https://graphql.anilist.co"
    DEFAULT_TIMEOUT = 15  # seconds
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 1  # seconds

    def __init__(
        self,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """
        Initialize the AniList client.

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
        Create a requests Session with retry logic and JSON headers.

        Returns:
            requests.Session: Configured session.
        """
        session = requests.Session()

        # Set up retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.RETRY_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers for GraphQL (JSON)
        session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        return session

    def _request(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a GraphQL POST request to the AniList API.

        Args:
            query: The GraphQL query string.
            variables: Optional variables for the query.

        Returns:
            Dict[str, Any]: The JSON response from the API.

        Raises:
            AniListNotFound: If the requested resource does not exist.
            AniListRateLimitError: On 429 Too Many Requests.
            AniListError: For other HTTP errors or GraphQL errors.
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            logger.debug(f"AniList GraphQL request: {query[:100]}... with variables {variables}")
            response = self.session.post(
                self.base_url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()

            # Check for GraphQL errors in response
            if "errors" in data:
                error_messages = [e.get("message", "Unknown error") for e in data["errors"]]
                error_str = ", ".join(error_messages)
                logger.error(f"AniList GraphQL errors: {error_str}")

                # If it's a "not found" type error (maybe invalid ID)
                if any("not found" in e.get("message", "").lower() for e in data["errors"]):
                    raise AniListNotFound(f"Resource not found: {error_str}")
                else:
                    raise AniListError(f"GraphQL error: {error_str}")

            return data

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None

            if status_code == 404:
                logger.info("AniList resource not found.")
                raise AniListNotFound("Resource not found.") from e
            elif status_code == 429:
                logger.warning("AniList rate limit exceeded.")
                raise AniListRateLimitError("Rate limit exceeded. Please try again later.") from e
            else:
                logger.error(f"AniList HTTP error {status_code}: {e}")
                raise AniListError(f"HTTP error {status_code}: {e.response.text}") from e

        except requests.exceptions.ConnectionError as e:
            logger.error(f"AniList connection error: {e}")
            raise AniListError("Connection error while communicating with AniList.") from e

        except requests.exceptions.Timeout as e:
            logger.error(f"AniList request timed out: {e}")
            raise AniListError("Request timed out.") from e

        except requests.exceptions.RequestException as e:
            logger.error(f"AniList request failed: {e}")
            raise AniListError(f"Request failed: {e}") from e

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from AniList: {e}")
            raise AniListError("Invalid JSON response from server.") from e

    # ------------------- Public Methods -------------------

    def search_anime(
        self,
        title: str,
        page: Optional[int] = 1,
        per_page: Optional[int] = 10,
        genre: Optional[str] = None,
        year: Optional[int] = None,
        status: Optional[str] = None,  # "FINISHED", "RELEASING", "NOT_YET_RELEASED", "CANCELLED", "HIATUS"
        format: Optional[str] = None,  # "TV", "TV_SHORT", "MOVIE", "OVA", "ONA", "SPECIAL", "MUSIC"
        sort: Optional[List[str]] = None,  # e.g., ["POPULARITY_DESC", "SCORE_DESC"]
    ) -> Dict[str, Any]:
        """
        Search for anime by title with optional filters.

        Args:
            title: The anime title to search for.
            page: Page number (default 1).
            per_page: Number of results per page (max 50, default 10).
            genre: Filter by genre name (exact match).
            year: Filter by season year.
            status: Filter by media status (FINISHED, RELEASING, etc.).
            format: Filter by media format (TV, MOVIE, etc.).
            sort: List of sort orders (e.g., ["POPULARITY_DESC", "SCORE_DESC"]).

        Returns:
            Dict[str, Any]: The raw AniList GraphQL response.

        Raises:
            AniListError: For any API or GraphQL error.
        """
        variables = {
            "search": title,
            "page": page or 1,
            "perPage": min(per_page or 10, 50),  # AniList max perPage is 50
        }
        if genre:
            variables["genre"] = genre
        if year:
            variables["year"] = year
        if status:
            variables["status"] = status.upper()
        if format:
            variables["format"] = format.upper()
        if sort:
            variables["sort"] = sort

        response = self._request(SEARCH_ANIME_QUERY, variables)
        return response

    def get_anime(self, anime_id: int) -> Dict[str, Any]:
        """
        Get detailed information about an anime by its AniList ID.

        Args:
            anime_id: The AniList media ID.

        Returns:
            Dict[str, Any]: The raw AniList GraphQL response.

        Raises:
            AniListNotFound: If the anime does not exist.
            AniListError: For any other API error.
        """
        variables = {"id": anime_id}
        response = self._request(GET_ANIME_QUERY, variables)
        # AniList may return null data if not found (but also errors)
        # We already handle errors; but if data is null, raise not found
        if response.get("data", {}).get("Media") is None:
            raise AniListNotFound(f"Anime with ID {anime_id} not found.")
        return response


# ------------------- Helper to get client instance -------------------

def get_anilist_client() -> AniListClient:
    """
    Factory function to get an AniListClient instance.

    Returns:
        AniListClient: Configured client.
    """
    return AniListClient()


# ------------------- Example usage (for testing) -------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG)

    client = AniListClient()
    try:
        # Search for "Naruto"
        results = client.search_anime("Naruto", per_page=3)
        if results.get("data", {}).get("Page", {}).get("media"):
            for anime in results["data"]["Page"]["media"]:
                print(f"{anime['title']['romaji']} (ID: {anime['id']})")

            # Get detailed info for the first result
            first_id = results["data"]["Page"]["media"][0]["id"]
            detail = client.get_anime(first_id)
            media = detail["data"]["Media"]
            print(f"\nDetail for {media['title']['romaji']}:")
            print(f"  Episodes: {media['episodes']}")
            print(f"  Status: {media['status']}")
            print(f"  Score: {media['averageScore']}")
        else:
            print("No results found.")
    except AniListError as e:
        print(f"Error: {e}", file=sys.stderr)