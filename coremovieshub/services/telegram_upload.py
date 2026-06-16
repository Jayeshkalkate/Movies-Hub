from telegram import Bot
from telegram.error import (
    TelegramError,
    TimedOut,
    NetworkError,
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
    - Retry logic (3 attempts)
    - Timeout handling
    - Network error handling

    Returns:
        telegram.Message
    """

    bot = get_bot()

    try:
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

                # Small files → upload as video
                else:

                    message = await bot.send_video(
                        chat_id=chat_id,
                        video=file_obj,
                        caption=caption,
                        supports_streaming=True,
                    )

                logger.info(
                    "Video uploaded successfully to channel %s",
                    chat_id
                )

                return message

            except (TimedOut, NetworkError):

                logger.warning(
                    "Upload attempt %s failed for channel %s",
                    attempt + 1,
                    chat_id,
                )

                if attempt == 2:
                    raise

                await asyncio.sleep(5)

        raise Exception("Upload failed after 3 attempts")

    except TimedOut:
        logger.exception(
            "Telegram upload timed out for channel %s",
            chat_id,
        )
        raise

    except NetworkError:
        logger.exception(
            "Telegram network error for channel %s",
            chat_id,
        )
        raise

    except TelegramError:
        logger.exception(
            "Telegram API error for channel %s",
            chat_id,
        )
        raise

    except Exception:
        logger.exception(
            "Unexpected error while uploading video to channel %s",
            chat_id,
        )
        raise