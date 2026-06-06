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
    if verification_code:
        try:
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

        except MembershipVerification.DoesNotExist:
            return "invalid_code"

    else:
        try:
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
            return "no_record"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id

    args = context.args
    verification_code = args[0] if args else None

    result = await verify_membership(
        telegram_id,
        verification_code
    )

    if result == "verified":
        await update.message.reply_text(
            "✅ Your MovieHub account has been verified!\n"
            "You can now access all content on the website."
        )

    elif result == "not_member":
        channel_link = settings.TELEGRAM_CHANNEL_ID

        await update.message.reply_text(
            f"❌ You are not a member of our channel.\n\n"
            f"Please join:\n{channel_link}\n\n"
            f"Then click /start again."
        )

    else:
        await update.message.reply_text(
            "⚠️ Invalid verification link.\n"
            "Please verify again from the website."
        )


# =====================================================
# MOVIE UPLOAD SYSTEM
# =====================================================

TITLE, CATEGORY_STATE, YEAR, QUALITY, UPLOAD = range(5)


def user_has_staff_access(user_id):
    return user_id in settings.TELEGRAM_ADMIN_IDS


@sync_to_async
def get_categories():
    return list(Category.objects.all())


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
    year,
    quality
):
    TelegramMovie.objects.create(
        title=title,
        category=category,
        channel=channel,
        telegram_message_id=message_id,
        telegram_file_id=file_id,
        year=year,
        quality=quality,
    )


async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if not user_has_staff_access(user_id):
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
    context.user_data["title"] = update.message.text

    categories = await get_categories()

    buttons = [
        [InlineKeyboardButton(
            cat.name,
            callback_data=str(cat.id)
        )]
        for cat in categories
    ]

    await update.message.reply_text(
        "📂 Choose category:",
        reply_markup=InlineKeyboardMarkup(buttons)
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

    if year_text.isdigit():
        context.user_data["year"] = int(year_text)
    else:
        context.user_data["year"] = None

    await update.message.reply_text(
        "🎥 Enter quality (720p / 1080p / 4K):"
    )

    return QUALITY


async def quality_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data["quality"] = update.message.text.strip()

    await update.message.reply_text(
        "📤 Send the movie video file now."
    )

    return UPLOAD


async def video_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    video = update.message.video

    if not video:
        await update.message.reply_text(
            "❌ Please send a video file."
        )
        return UPLOAD

    try:
        category = await get_category(
            context.user_data["category_id"]
        )

        target_channel = await get_channel_for_category(
            category
        )

    except TelegramChannel.DoesNotExist:
        await update.message.reply_text(
            f"❌ No Telegram channel configured for {category.name}"
        )
        return ConversationHandler.END

    caption = (
        f"🎬 {context.user_data['title']}\n"
        f"📅 Year: {context.user_data['year']}\n"
        f"🎥 Quality: {context.user_data['quality']}"
    )

    sent = await context.bot.send_video(
        chat_id=target_channel.chat_id,
        video=video.file_id,
        caption=caption,
        supports_streaming=True
    )

    await save_movie(
        title=context.user_data["title"],
        category=category,
        channel=target_channel,
        message_id=sent.message_id,
        file_id=video.file_id,
        year=context.user_data["year"],
        quality=context.user_data["quality"]
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


@sync_to_async
def search_movie_db(query):
    return list(
        TelegramMovie.objects.filter(
            title__icontains=query
        ).select_related(
            "category",
            "channel"
        )[:10]
    )

async def search_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage:\n/search movie_name")
        return

    query = " ".join(context.args).strip()
    results = await search_movie_db(query)

    if not results:
        await update.message.reply_text("❌ No movies found.")
        return

    for movie in results:
        category = movie.category.name if movie.category else "Unknown"
        year = movie.year or "N/A"
        quality = movie.quality or "N/A"

        # Build deep link to the Telegram message
        # chat_id is like "-1001234567890" – remove "-100" to get public part
        chat_link_part = movie.channel.chat_id
        if chat_link_part.startswith("-100"):
            chat_link_part = chat_link_part[4:]   # remove "-100"
        message_link = f"https://t.me/c/{chat_link_part}/{movie.telegram_message_id}"

        text = (
            f"🎬 *{movie.title}*\n"
            f"📂 Category: {category}\n"
            f"📅 Year: {year}\n"
            f"🎥 Quality: {quality}\n\n"
            f"🔗 [Watch on Telegram]({message_link})"
        )
        await update.message.reply_text(text, parse_mode='Markdown', disable_web_page_preview=True)
        
