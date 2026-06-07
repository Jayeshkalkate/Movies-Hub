from telegram import Bot

from django.conf import settings

import logging

from telegram.error import (
    TelegramError,
    TimedOut,
    NetworkError,
)

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
    Returns Telegram Message object.
    """

    bot = get_bot()

    try:
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

    except TimedOut:
        logger.exception(
            "Telegram upload timed out for channel %s",
            chat_id
        )
        raise

    except NetworkError:
        logger.exception(
            "Telegram network error for channel %s",
            chat_id
        )
        raise

    except TelegramError:
        logger.exception(
            "Telegram API error for channel %s",
            chat_id
        )
        raise

    except Exception:
        logger.exception(
            "Unexpected error while uploading video to channel %s",
            chat_id
        )
        raise