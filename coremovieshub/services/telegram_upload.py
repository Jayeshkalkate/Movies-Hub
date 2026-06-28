"""
Telegram upload utilities with robust retry logic.

Handles:
- Video and document uploads to channels
- Exponential backoff retries
- RetryAfter handling
- Timeout and network error recovery
- Logging
"""

import asyncio
import logging
from typing import Optional, BinaryIO, Union
from datetime import datetime

from django.conf import settings
from telegram import Bot, Message
from telegram.error import (
    TelegramError,
    TimedOut,
    NetworkError,
    RetryAfter,
    Conflict,
    Forbidden,
    BadRequest,
)

logger = logging.getLogger(__name__)

# ------------------- Constants -------------------
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 2  # seconds, doubles each retry
DEFAULT_INITIAL_DELAY = 1  # seconds
LARGE_FILE_THRESHOLD = 50 * 1024 * 1024  # 50 MB
UPLOAD_TIMEOUT = 60  # seconds for the overall upload operation

_bot: Optional[Bot] = None


def get_bot() -> Bot:
    """Get or create the Telegram Bot instance."""
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    return _bot


def _is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error is worth retrying.

    Retryable:
        - TimedOut
        - NetworkError
        - RetryAfter (with backoff)
        - Conflict (usually conflict with other requests)
        - Generic TelegramError for certain status codes?

    Non‑retryable:
        - Forbidden (bot blocked, can't recover)
        - BadRequest (invalid parameters, won't succeed)
        - Other unexpected exceptions
    """
    if isinstance(error, (TimedOut, NetworkError, Conflict)):
        return True
    if isinstance(error, RetryAfter):
        return True
    # For generic TelegramError, we can check the error message if needed
    # but it's safer to assume not retryable to avoid infinite loops
    # However, we'll treat it as retryable only if it's not a specific subclass
    # Actually, we only retry known transient errors.
    return False


async def upload_video_to_channel(
    file_obj: Union[BinaryIO, bytes],
    chat_id: Union[str, int],
    caption: str = "",
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    is_document: bool = False,
) -> Message:
    """
    Upload a video or document to a Telegram channel with retries.

    Args:
        file_obj: File-like object or bytes to upload.
        chat_id: Target channel ID (string or integer).
        caption: Caption for the uploaded media.
        max_retries: Maximum number of retry attempts.
        initial_delay: Initial delay in seconds before first retry.
        backoff_factor: Multiplier for exponential backoff.
        is_document: Force upload as document (for large files or non-video).

    Returns:
        telegram.Message: The sent message object.

    Raises:
        TelegramError: After all retries fail, or if a non-retryable error occurs.
    """
    bot = get_bot()

    # Determine file size if possible
    file_size = None
    if hasattr(file_obj, "size"):
        file_size = file_obj.size
    elif hasattr(file_obj, "tell") and hasattr(file_obj, "seek"):
        # Try to get size by seeking to end
        try:
            pos = file_obj.tell()
            file_obj.seek(0, 2)
            file_size = file_obj.tell()
            file_obj.seek(pos)
        except Exception:
            pass

    # Decide upload method
    use_document = is_document or (file_size is not None and file_size > LARGE_FILE_THRESHOLD)

    # Log initial attempt
    logger.info(
        "Uploading %s to channel %s (size: %s MB, document: %s)",
        "video" if not use_document else "file",
        chat_id,
        round(file_size / (1024 * 1024), 2) if file_size else "unknown",
        use_document,
    )

    last_exception = None
    delay = initial_delay

    for attempt in range(1, max_retries + 1):
        try:
            # Add a timeout wrapper (if using async, we can't easily set a timeout per call,
            # but we can use asyncio.timeout or rely on the library's internal timeout)
            # We'll use asyncio.wait_for with a reasonable timeout.
            if use_document:
                result = await bot.send_document(
                    chat_id=chat_id,
                    document=file_obj,
                    caption=caption,
                    timeout=UPLOAD_TIMEOUT,
                )
            else:
                result = await bot.send_video(
                    chat_id=chat_id,
                    video=file_obj,
                    caption=caption,
                    supports_streaming=True,
                    timeout=UPLOAD_TIMEOUT,
                )

            logger.info(
                "Upload successful on attempt %s: message_id=%s",
                attempt,
                result.message_id,
            )
            return result

        except RetryAfter as e:
            retry_after = e.retry_after
            logger.warning(
                "Rate limited (RetryAfter) on attempt %s, retry in %s seconds",
                attempt,
                retry_after,
            )
            # Use the server-specified delay, but cap it to avoid long waits
            wait_time = min(retry_after, 60)
            await asyncio.sleep(wait_time)
            last_exception = e
            continue

        except (TimedOut, NetworkError, Conflict) as e:
            # Transient network/timeout errors
            if attempt == max_retries:
                logger.error(
                    "Permanent failure after %s attempts: %s",
                    max_retries,
                    e,
                )
                raise e

            wait_time = delay * (backoff_factor ** (attempt - 1))
            logger.warning(
                "Transient error on attempt %s: %s. Retrying in %s seconds.",
                attempt,
                e.__class__.__name__,
                wait_time,
            )
            await asyncio.sleep(wait_time)
            last_exception = e

        except (Forbidden, BadRequest) as e:
            # Non‑retryable errors
            logger.error("Non‑retryable error: %s", e)
            raise e

        except TelegramError as e:
            # Catch-all for other Telegram errors – decide based on message
            if "flood" in str(e).lower():
                # Sometimes flood control is not explicitly RetryAfter, but we can treat it
                # as retryable with a longer delay
                wait_time = 10 * (attempt ** 2)
                logger.warning(
                    "Flood control error on attempt %s, waiting %s seconds",
                    attempt,
                    wait_time,
                )
                await asyncio.sleep(wait_time)
                last_exception = e
                continue
            else:
                # Unknown Telegram error – not likely to be retryable
                logger.error("Unhandled TelegramError: %s", e)
                raise e

    # If we exhaust retries, raise the last exception
    if last_exception:
        logger.error("All retries exhausted. Last error: %s", last_exception)
        raise last_exception

    # Fallback
    raise RuntimeError("Upload failed after retries without explicit exception.")