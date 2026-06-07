from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async

from coremovieshub.models import (
    MembershipVerification,
    Category,
    TelegramChannel,
    TelegramMovie,
)

from coremovieshub.telegram_utils import check_telegram_membership


# =====================================================
# MEMBERSHIP VERIFICATION
# =====================================================

@sync_to_async
def verify_membership(telegram_id, verification_code=None):
    try:
        if verification_code:
            verification = MembershipVerification.objects.get(
                verification_code=verification_code
            )

            verification.telegram_id = str(telegram_id)
            verification.save()

            if check_telegram_membership(telegram_id):
                verification.membership_status = True
                verification.verified_at = timezone.now()
                verification.save()
                return "verified"

            return "not_member"

        verification = MembershipVerification.objects.get(
            telegram_id=str(telegram_id)
        )

        if check_telegram_membership(telegram_id):
            verification.membership_status = True
            verification.verified_at = timezone.now()
            verification.save()
            return "verified"

        return "not_member"

    except MembershipVerification.DoesNotExist:
        return "invalid_code"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id

    verification_code = context.args[0] if context.args else None

    result = await verify_membership(
        telegram_id,
        verification_code
    )

    if result == "verified":
        await update.message.reply_text(
            "✅ Your MovieHub account has been verified!\n\n"
            "You can now access all content on the website."
        )

    elif result == "not_member":
        await update.message.reply_text(
            "❌ You are not a member of the required channel.\n\n"
            "Please join the channel and try again."
        )

    else:
        await update.message.reply_text(
            "⚠️ Invalid verification link."
        )


# =====================================================
# MOVIE UPLOAD SYSTEM
# =====================================================

TITLE, CATEGORY_STATE, YEAR, QUALITY, UPLOAD = range(5)


def user_has_staff_access(user_id):
    return user_id in settings.TELEGRAM_ADMIN_IDS


@sync_to_async
def get_categories():
    return list(Category.objects.order_by("name"))


@sync_to_async
def get_category(category_id):
    return Category.objects.get(id=category_id)


@sync_to_async
def get_channel_for_category(category):
    return TelegramChannel.objects.get(category=category)


@sync_to_async
def save_movie(
    title,
    category,
    channel,
    message_id,
    file_id,
    message_link,
    year,
    quality,
):
    TelegramMovie.objects.create(
        title=title,
        category=category,
        channel=channel,
        telegram_message_id=message_id,
        telegram_file_id=file_id,
        telegram_message_link=message_link,
        year=year,
        quality=quality,
    )


async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not user_has_staff_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ Only administrators can upload movies."
        )
        return ConversationHandler.END

    context.user_data.clear()

    await update.message.reply_text(
        "🎬 Enter movie title:"
    )

    return TITLE


async def title_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data["title"] = update.message.text.strip()

    categories = await get_categories()

    if not categories:
        await update.message.reply_text(
            "❌ No categories found."
        )
        return ConversationHandler.END

    keyboard = [
        [
            InlineKeyboardButton(
                category.name,
                callback_data=str(category.id)
            )
        ]
        for category in categories
    ]

    await update.message.reply_text(
        "📂 Choose category:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return CATEGORY_STATE


async def category_chosen(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    await query.answer()

    context.user_data["category_id"] = int(query.data)

    await query.edit_message_text(
        "📅 Enter release year:"
    )

    return YEAR


async def year_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    year_text = update.message.text.strip()

    context.user_data["year"] = (
        int(year_text)
        if year_text.isdigit()
        else None
    )

    await update.message.reply_text(
        "🎥 Enter quality (480p / 720p / 1080p / 4K):"
    )

    return QUALITY


async def quality_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data["quality"] = update.message.text.strip()

    await update.message.reply_text(
        "📤 Send the movie file now."
    )

    return UPLOAD


async def video_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    video = update.message.video

    if not video:
        await update.message.reply_text(
            "❌ Please send a Telegram video."
        )
        return UPLOAD

    try:
        category = await get_category(
            context.user_data["category_id"]
        )

        target_channel = await get_channel_for_category(
            category
        )

    except Category.DoesNotExist:
        await update.message.reply_text(
            "❌ Category not found."
        )
        return ConversationHandler.END

    except TelegramChannel.DoesNotExist:
        await update.message.reply_text(
            "❌ No Telegram channel configured for this category."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "⏳ Uploading movie..."
    )

    caption = (
        f"🎬 {context.user_data['title']}\n"
        f"📅 Year: {context.user_data['year'] or 'N/A'}\n"
        f"🎥 Quality: {context.user_data['quality']}"
    )

    sent_message = await context.bot.send_video(
        chat_id=target_channel.chat_id,
        video=video.file_id,
        caption=caption,
        supports_streaming=True
    )

    chat_id = str(target_channel.chat_id)

    if chat_id.startswith("-100"):
        chat_id = chat_id[4:]

    message_link = (
        f"https://t.me/c/"
        f"{chat_id}/"
        f"{sent_message.message_id}"
    )

    await save_movie(
        title=context.user_data["title"],
        category=category,
        channel=target_channel,
        message_id=sent_message.message_id,
        file_id=video.file_id,
        message_link=message_link,
        year=context.user_data["year"],
        quality=context.user_data["quality"],
    )

    await update.message.reply_text(
        f"✅ Movie uploaded successfully!\n\n"
        f"🎬 {context.user_data['title']}"
    )

    context.user_data.clear()

    return ConversationHandler.END


async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()

    await update.message.reply_text(
        "❌ Upload cancelled."
    )

    return ConversationHandler.END


# =====================================================
# SEARCH MOVIES
# =====================================================

@sync_to_async
def search_movie_db(query):
    return list(
        TelegramMovie.objects.filter(
            title__icontains=query
        )
        .select_related(
            "category",
            "channel"
        )[:10]
    )


async def search_movies(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not context.args:
        await update.message.reply_text(
            "Usage:\n/search movie_name"
        )
        return

    query = " ".join(context.args).strip()

    movies = await search_movie_db(query)

    if not movies:
        await update.message.reply_text(
            "❌ No movies found."
        )
        return

    for movie in movies:

        category = (
            movie.category.name
            if movie.category
            else "Unknown"
        )

        year = movie.year or "N/A"
        quality = movie.quality or "N/A"

        chat_id = str(movie.channel.chat_id)

        if chat_id.startswith("-100"):
            chat_id = chat_id[4:]

        message_link = (
            f"https://t.me/c/"
            f"{chat_id}/"
            f"{movie.telegram_message_id}"
        )

        text = (
            f"🎬 *{movie.title}*\n"
            f"📂 Category: {category}\n"
            f"📅 Year: {year}\n"
            f"🎥 Quality: {quality}\n\n"
            f"🔗 [Watch on Telegram]({message_link})"
        )

        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        
