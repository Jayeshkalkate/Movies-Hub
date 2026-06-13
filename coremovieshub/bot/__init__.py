# coremovieshub/bot/__init__.py

from django.conf import settings
from .handlers import handle_channel_post

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from asgiref.sync import async_to_sync

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
    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("search", search_movies)
    )

    # Upload Conversation
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler(
                "upload",
                upload_start,
            )
        ],
        states={
            TITLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    title_received,
                )
            ],
            CATEGORY_STATE: [
                CallbackQueryHandler(
                    category_chosen
                )
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
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    application.add_handler(conv_handler)
    
    # application.add_handler(
    #     MessageHandler(
    #         filters.ChatType.CHANNEL,
    #         handle_channel_post
    #         )
    #     )
    
    application.add_handler(
        MessageHandler(
            (
                filters.UpdateType.CHANNEL_POST
                | filters.ChatType.SUPERGROUP
                )
            &
            (filters.VIDEO | filters.Document.ALL),
            handle_channel_post,
            )
        )

    return application


def get_application():
    """
    Create a fresh PTB Application.
    Prevents Render's 'Event loop is closed' error.
    """
    app = setup_bot()

    async_to_sync(app.initialize)()

    return app

