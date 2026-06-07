# coremovieshub/bot/__init__.py

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from django.conf import settings

from .handlers import (
    start,
    upload_start,
    title_received,
    category_chosen,
    year_received,
    quality_received,
    video_received,
    cancel,
    search_movies,
    TITLE,
    CATEGORY_STATE,
    YEAR,
    QUALITY,
    UPLOAD,
)


def setup_bot():
    application = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .build()
    )

    # Basic Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search_movies))

    # Upload Conversation
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("upload", upload_start)
        ],
        states={
            TITLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    title_received,
                )
            ],
            CATEGORY_STATE: [
                CallbackQueryHandler(category_chosen)
            ],
            YEAR: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    year_received,
                )
            ],
            QUALITY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    quality_received,
                )
            ],
            UPLOAD: [
                MessageHandler(
                    filters.VIDEO,
                    video_received,
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
    )

    application.add_handler(conv_handler)

    return application

from asgiref.sync import async_to_sync

_app = None
_initialized = False

def get_application():
    global _app
    global _initialized

    if _app is None:
        _app = setup_bot()

    if not _initialized:
        async_to_sync(_app.initialize)()
        _initialized = True

    return _app