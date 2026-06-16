from telegram import Bot
from telegram.error import (
    TelegramError,
    TimedOut,
    NetworkError,
    RetryAfter,          # <-- NEW
)

from django.conf import settings

import logging
import asyncio

logger = logging.getLogger(__name__)

_bot = None


def get_bot():
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    return _bot


async def upload_video_to_channel(
    file_obj,
    chat_id,
    caption=""
):
    """
    Upload video to Telegram channel.

    Small files  -> send_video()
    Large files  -> send_document()

    Includes:
    - Retry logic (3 attempts) with exponential backoff for network/timeout errors
    - Specific handling for RetryAfter (rate limiting) – sleeps exactly the required time
    - Timeout and network error handling

    Returns:
        telegram.Message
    """
    bot = get_bot()
    file_size = file_obj.size

    for attempt in range(3):
        try:
            # Large files → upload as document
            if file_size > 50 * 1024 * 1024:
                message = await bot.send_document(
                    chat_id=chat_id,
                    document=file_obj,
                    caption=caption,
                )
            else:
                message = await bot.send_video(
                    chat_id=chat_id,
                    video=file_obj,
                    caption=caption,
                    supports_streaming=True,
                )

            logger.info("Video uploaded successfully to channel %s", chat_id)
            return message

        except RetryAfter as e:
            # Rate limit – wait exactly as requested and then retry
            retry_after = e.retry_after
            logger.warning(
                "Rate limited on channel %s. Retry after %s seconds. Attempt %s/3",
                chat_id, retry_after, attempt + 1
            )
            await asyncio.sleep(retry_after)
            # Continue to next attempt (do not count this as a failure)

        except (TimedOut, NetworkError) as e:
            # Transient network issues – back off and retry
            wait = 5 * (attempt + 1)  # simple exponential backoff
            logger.warning(
                "Network/timeout error on channel %s (attempt %s/3). Retrying in %s seconds.",
                chat_id, attempt + 1, wait
            )
            if attempt == 2:
                raise  # re-raise after final attempt
            await asyncio.sleep(wait)

        except TelegramError as e:
            # Other Telegram API errors (e.g., bad request, permission)
            logger.exception(
                "Telegram API error for channel %s: %s",
                chat_id, str(e)
            )
            raise

        except Exception as e:
            # Any unexpected error
            logger.exception(
                "Unexpected error while uploading video to channel %s: %s",
                chat_id, str(e)
            )
            raise

    # If we exit the loop without returning, all attempts failed
    raise Exception(f"Upload failed after 3 attempts to channel {chat_id}")