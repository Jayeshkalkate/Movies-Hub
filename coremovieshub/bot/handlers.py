import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
logger = logging.getLogger(__name__)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)
from coremovieshub.services.movie_metadata import search_movie_metadata
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from coremovieshub.models import (
    MembershipVerification,
    Category,
    TelegramChannel,
    TelegramMovie,
)

from coremovieshub.telegram_utils import check_telegram_membership

from coremovieshub.utils.movie_parser import (
    clean_caption,
    extract_title,
    extract_quality,
    extract_language,
    extract_season,
)

REQUIRED_CHANNELS = [
    settings.MAIN_CHANNEL_ID,
]

# =====================================================
# MEMBERSHIP VERIFICATION
# =====================================================
@sync_to_async
def verify_membership(telegram_id, verification_code=None):
    try:

        # Verification via deep-link code
        if verification_code:

            verification = (
                MembershipVerification.objects
                .filter(
                    verification_code=verification_code
                    )
                .first()
                )
            
            if not verification:
                return "invalid_code"

            verification.telegram_id = str(telegram_id)
            verification.telegram_username = (
                f"@{verification.user.username}"
                if verification.user
                else ""
                )
            
            verification.save()

            all_joined = all(
                check_telegram_membership(
                    telegram_id,
                    channel
                    )
                for channel in REQUIRED_CHANNELS
                )
            if all_joined:

                verification.membership_status = True
                verification.verified_at = timezone.now()
                verification.save()

                return "verified"

            return "not_member"

        # Verification using stored telegram_id
        verification, created = MembershipVerification.objects.get_or_create(
            telegram_id=str(telegram_id),
            defaults={
                "membership_status": False,
            }
        )

        if not verification:
            return "verification_not_found"

        all_joined = all(
            check_telegram_membership(
                telegram_id,
                channel
                )
            for channel in REQUIRED_CHANNELS
            )
        
        if all_joined:

            verification.membership_status = True
            verification.verified_at = timezone.now()
            verification.save()

            return "verified"

        return "not_member"

    except MembershipVerification.DoesNotExist:
        return "invalid_code"

    except Exception:
        logger.exception(
            "Membership verification failed"
        )
        return "error"

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not user:
        return

    telegram_id = user.id

    logger.info(
        "START command received from Telegram ID: %s",
        telegram_id
    )

    raw_code = (
        context.args[0].strip()
        if context.args
        else None
    )

    verification_code = None

    logger.info(
        "Raw start parameter received: %s",
        raw_code
    )

    # =====================================================
    # VERIFICATION DEEP LINK
    # =====================================================
    if raw_code and raw_code.startswith("verify_"):

        verification_code = raw_code.replace(
            "verify_",
            "",
            1
        ).strip()

        logger.info(
            "Verification code extracted: %s",
            verification_code
        )

    # =====================================================
    # NORMAL /START
    # =====================================================
    elif not raw_code:

        keyboard = [
            [
                InlineKeyboardButton(
                    "🌐 Open Website",
                    url=settings.BASE_URL
                )
            ]
        ]

        await update.message.reply_text(
            "🎬 Welcome to MoviesHub!\n\n"
            "To access movies:\n"
            "1️⃣ Register on website\n"
            "2️⃣ Login\n"
            "3️⃣ Verify Telegram\n"
            "4️⃣ Join required channels\n"
            "5️⃣ Start watching movies",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    # =====================================================
    # INVALID PARAMETER
    # =====================================================
    else:

        await update.message.reply_text(
            "⚠️ Invalid verification link.\n\n"
            "Please return to MoviesHub and generate a new verification link."
        )

        return

    # =====================================================
    # VERIFY MEMBERSHIP
    # =====================================================
    try:

        result = await verify_membership(
            telegram_id,
            verification_code
        )

        logger.info(
            "Verification result for %s: %s",
            telegram_id,
            result
        )

        if result == "verified":
            
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🎬 Open MoviesHub",
                        url=settings.BASE_URL
                        )
                    ]
                ]
            
            await update.message.reply_text(
                "✅ Account verified successfully!\n\n"
                "You can now return to MoviesHub and continue.",
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                    )
                )

        elif result == "not_member":

            await update.message.reply_text(
                "❌ Verification failed.\n\n"
                "Please join the required Telegram channel and try again."
            )

        elif result == "invalid_code":

            await update.message.reply_text(
                "⚠️ Invalid or expired verification link.\n\n"
                "Please return to MoviesHub and generate a new verification link."
            )

        elif result == "verification_not_found":

            await update.message.reply_text(
                "⚠️ Verification record not found."
            )

        else:

            await update.message.reply_text(
                "⚠️ Verification could not be completed.\n\n"
                "Please try again later."
            )
            
    except Exception:
        logger.exception(
            "Error during verification for Telegram ID %s",
            telegram_id,
        )
        
        await update.message.reply_text(
            "❌ An unexpected error occurred while processing "
            "your verification request.\n\n"
            "Please try again later."
        )
        
# =====================================================
# MOVIE UPLOAD SYSTEM
# =====================================================

TITLE, CATEGORY_STATE, YEAR, QUALITY, UPLOAD = range(5)


# Improvement 1: Safer admin check
def user_has_staff_access(user_id):
    try:
        admin_ids = {
            int(x)
            for x in getattr(
                settings,
                "TELEGRAM_ADMIN_IDS",
                []
            )
            if str(x).strip()
        }

        return int(user_id) in admin_ids

    except Exception:
        return False


@sync_to_async
def get_categories():
    return list(Category.objects.order_by("name"))


# Improvement 4: Prevent crash if category does not exist
@sync_to_async
def get_category(category_id):
    return Category.objects.filter(id=category_id).first()


@sync_to_async
def get_channel_for_category(category):
    return TelegramChannel.objects.filter(category=category).first()
    # return TelegramChannel.objects.get(category=category)


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
    release_date,
    description="",
):
    TelegramMovie.objects.create(
        title=title,
        category=category,
        channel=channel,
        release_date=release_date,
        telegram_message_id=message_id,
        telegram_file_id=file_id,
        telegram_message_link=message_link,
        year=year,
        quality=quality,
        description=clean_caption(description),
        language=extract_language(description),
        season=extract_season(description),
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


async def title_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    context.user_data["category_id"] = int(query.data)

    await query.edit_message_text(
        "📅 Enter release year:"
    )

    return YEAR


# Improvement 2: Better year validation
async def year_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    year_text = update.message.text.strip()

    if year_text.isdigit():
        year = int(year_text)

        if 1900 <= year <= timezone.now().year + 1:
            context.user_data["year"] = year
        else:
            context.user_data["year"] = None
    else:
        context.user_data["year"] = None

    await update.message.reply_text(
        "🎥 Enter quality (480p / 720p / 1080p / 4K):"
    )

    return QUALITY


async def quality_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["quality"] = update.message.text.strip()

    await update.message.reply_text(
        "📤 Send the movie file now."
    )

    return UPLOAD


async def video_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = ( update.message.video or update.message.document )

    if not video:
        await update.message.reply_text(
            "❌ Please send a Telegram video."
        )
        return UPLOAD

    # Improvement 4: Check if category exists
    category = await get_category(context.user_data["category_id"])

    if not category:
        await update.message.reply_text(
            "❌ Category not found."
        )
        return ConversationHandler.END

    # try:
    target_channel = await get_channel_for_category(
            category
        )
        
    if not target_channel:
        await update.message.reply_text(
            "❌ No Telegram channel configured for this category."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "⏳ Uploading movie..."
    )

    # Improvement 3: Handle missing year key safely
    caption = (
        f"🎬 {context.user_data['title']}\n"
        f"📅 Year: {context.user_data.get('year', 'N/A')}\n"
        f"🎥 Quality: {context.user_data['quality']}"
    )

    if update.message.video:
        sent_message = await context.bot.send_video(
            chat_id=target_channel.chat_id,
            video=video.file_id,
            caption=caption,
            supports_streaming=True,
    )
        
    else:
        sent_message = await context.bot.send_document(
            chat_id=target_channel.chat_id,
            document=video.file_id,
            caption=caption,
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
        year=context.user_data.get("year"),
        quality=context.user_data["quality"],
    )

    await update.message.reply_text(
        f"✅ Movie uploaded successfully!\n\n"
        f"🎬 {context.user_data['title']}"
    )

    context.user_data.clear()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            ).order_by(
                "-created_at"
                )
        .select_related(
            "category",
            "channel"
        )[:10]
    )


async def search_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        category = movie.category.name if movie.category else "Unknown"
        year = movie.year or "N/A"
        quality = movie.quality or "N/A"

        # Improvement 5: Prefer stored message link, fallback to constructed one
        if movie.telegram_message_link:
            message_link = movie.telegram_message_link
        else:
            chat_id = str(movie.channel.chat_id)
            if chat_id.startswith("-100"):
                chat_id = chat_id[4:]
            message_link = f"https://t.me/c/{chat_id}/{movie.telegram_message_id}"

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
@sync_to_async
def save_channel_movie(post, channel, media):
    caption = post.caption or ""

    title = extract_title(caption)

    if not title:
        title = (
            getattr(media, "file_name", None)
            or "Untitled Movie"
        )

    chat_id = str(channel.chat_id)

    if chat_id.startswith("-100"):
        chat_id = chat_id[4:]

    message_link = (
        f"https://t.me/c/{chat_id}/{post.message_id}"
    )

    logger.info("=" * 60)
    logger.info("SAVE_CHANNEL_MOVIE STARTED")
    logger.info("TITLE: %s", title)
    logger.info("MESSAGE ID: %s", 
                post.message_id,
    )
    logger.info(
        "CHANNEL ID: %s",
        channel.chat_id,
    )
    logger.info(
        "MESSAGE LINK: %s",
        message_link,
    )
    logger.info(
        "MEDIA TYPE: %s",
        type(media).__name__,
    )
    logger.info(
        "FILE ID: %s",
        media.file_id,
    )
    logger.info("=" * 60)

    try:
        # Fetch metadata from TMDB
        metadata = search_movie_metadata(
            title
        )

        poster = None
        banner = None
        overview = clean_caption(caption)
        rating = None
        release_date = None
        
        if metadata:
            
            poster = (
                metadata.get("poster")
                or poster
            )
            
            banner = (
                metadata.get("banner")
                or banner
            )
            
            overview = (
                metadata.get("overview")
                or overview
            )
            
            rating = (
                metadata.get("rating")
                or rating
            )
            
            release_date = (
                metadata.get("release_date")
                or release_date
            )
            
        if not banner:
            banner = poster
        
        movie, created = TelegramMovie.objects.get_or_create(
            telegram_message_id=post.message_id,
            channel=channel,
            defaults={
                "title": title[:255],
                "content_type": "movie",
                "category": channel.category,
                "release_date": release_date,
                "telegram_file_id": media.file_id,
                "telegram_message_link": message_link,
                "quality": extract_quality(caption),
                "description": clean_caption(caption),
                "poster": poster,
                "banner": banner,
                "overview": overview,
                "rating": rating,
                "file_size": (
                    f"{round(media.file_size / (1024 ** 3), 2)} GB"
                    if getattr(media, "file_size", None)
                    and media.file_size >= (1024 ** 3)
                    else (
                        f"{round(media.file_size / (1024 ** 2), 2)} MB"
                        if getattr(media, "file_size", None)
                        else ""
                    )
                ),
                "duration": (
                    str(media.duration)
                    if getattr(media, "duration", None)
                    else ""
                ),
                "file_size_bytes": getattr(
                    media,
                    "file_size",
                    None,
                ),
            },
        )
                            
        if not created:
            logger.info("MOVIE ALREADY EXISTS")
            return movie

        
        logger.info("DATABASE ID: %s", movie.pk)
        logger.info("TITLE: %s", movie.title)
        logger.info("MESSAGE ID: %s", movie.telegram_message_id)
        logger.info("POSTER: %s", poster)
        logger.info("RATING: %s", rating)
        logger.info("=" * 60)
        return movie

    except Exception:
        logger.exception(
            "DATABASE SAVE FAILED"
        )
        
        raise
        
async def handle_channel_post(update, context):
    logger.info("=" * 60)
    logger.info("CHANNEL HANDLER FIRED")

    # post = update.channel_post
    
    post = update.channel_post or update.message
    
    if not post:
        return

    if not post:
        logger.info("NO CHANNEL POST")
        return
    
    logger.info(
        "CHAT ID: %s",
        post.chat.id,
    )
    
    logger.info(
        "VIDEO: %s",
        bool(post.video),
    )
    
    logger.info(
        "DOCUMENT: %s",
        bool(post.document),
    )
    
    logger.info(
        "CAPTION: %s",
        post.caption,
    )
    
    # Support both videos and MKV documents
    media = post.video or post.document

    if not media:
        logger.info("NO VIDEO OR DOCUMENT FOUND")
        return

    if post.document:
        logger.info(
            "DOCUMENT NAME:",
            getattr(post.document, "file_name", "Unknown")
        )

    if post.video:
        logger.info("VIDEO RECEIVED")

    chat_id = str(post.chat.id)

    channel = await sync_to_async(
        lambda: TelegramChannel.objects.select_related(
            "category"
        ).filter(
            chat_id=chat_id
        ).first()
    )()
    
    if not channel:
        logger.warning(
            "CHANNEL NOT FOUND: %s",
            chat_id,
        )
        return

    logger.info("CHANNEL FOUND ID: %s", channel.id)
    logger.info("CHANNEL FOUND NAME: %s", channel.name)
    logger.info("CHANNEL CHAT ID: %s", channel.chat_id)
    # message_link = (
    #     f"https://t.me/c/"
    #     f"{chat_id_for_link}/"
    #     f"{post.message_id}"
    # )
    # logger.info(
    #     "MESSAGE LINK: %s",
    #     message_link,
    # )
    
    try:
        caption = post.caption or ""

        title = (
            caption.split("\n")[0]
            .replace("🎬", "")
            .strip()
        )

        if not title:
            title = (
                getattr(media, "file_name", None)
                or "Untitled Movie"
            )

        # Build Telegram message link
        chat_id_for_link = str(post.chat.id)

        if chat_id_for_link.startswith("-100"):
            chat_id_for_link = chat_id_for_link[4:]

        message_link = (
            f"https://t.me/c/"
            f"{chat_id_for_link}/"
            f"{post.message_id}"
        )

        await save_channel_movie(
            post,
            channel,
            media
            )

        logger.info("✅ MOVIE SAVED SUCCESSFULLY")

    except Exception:
        logger.exception(
            "DATABASE SAVE FAILED"
        )

    logger.info("=" * 60)