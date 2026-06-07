from telegram import Bot
from django.conf import settings

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

    message = await bot.send_video(
        chat_id=chat_id,
        video=file_obj,
        caption=caption,
        supports_streaming=True
    )

    return message

