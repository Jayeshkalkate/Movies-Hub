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

application = None


def setup_bot():
    """Create and configure the Telegram bot application."""

    application = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search_movies))

    # Movie Upload Conversation
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("upload", upload_start)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title_received)],
            CATEGORY_STATE: [CallbackQueryHandler(category_chosen)],   # <-- per_message removed
            YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, year_received)],
            QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quality_received)],
            UPLOAD: [MessageHandler(filters.VIDEO, video_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    return application