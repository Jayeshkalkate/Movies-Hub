from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)
from coremovieshub.utils.movie_metadata import (
    search_movie_metadata,
)
from asgiref.sync import sync_to_async
import traceback
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

from coremovieshub.models import (
    MembershipVerification,
    Category,
    TelegramChannel,
    TelegramMovie,
)

from coremovieshub.telegram_utils import check_telegram_membership
import logging

from coremovieshub.utils.movie_parser import (
    clean_caption,
    extract_title,
    extract_quality,
    extract_language,
    extract_season,
)

logger = logging.getLogger(__name__)

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

    except Exception as e:
        print(f"Membership verification error: {e}")
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

    except Exception as e:

        logger.exception(
            "Error during verification for Telegram ID %s: %s",
            telegram_id,
            str(e)
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
    admin_ids = getattr(settings, "TELEGRAM_ADMIN_IDS", [])
    return int(user_id) in [int(x) for x in admin_ids]


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
    video = update.message.video

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

    try:
        target_channel = await get_channel_for_category(category)
    except TelegramChannel.DoesNotExist:
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

    print("=" * 60)
    print("SAVE_CHANNEL_MOVIE STARTED")
    print("TITLE:", title)
    print("MESSAGE ID:", post.message_id)
    print("CHANNEL ID:", channel.chat_id)
    print("MESSAGE LINK:", message_link)
    print("MEDIA TYPE:", type(media).__name__)
    print("FILE ID:", media.file_id)
    print("=" * 60)

    # Duplicate check
    existing = TelegramMovie.objects.filter(
        telegram_message_id=post.message_id,
        channel=channel,
    ).exists()

    if existing:
        print("=" * 60)
        print("MOVIE ALREADY EXISTS")
        print("MESSAGE ID:", post.message_id)
        print("=" * 60)
        return None

    try:
        # Fetch metadata from TMDB
        metadata = search_movie_metadata(
            title
        )

        poster = ""
        banner = ""
        overview = ""
        rating = None
        release_date = None

        if metadata:
            release_date = metadata.get("release_date")
            poster = metadata["poster"]
            banner = metadata["banner"]
            overview = metadata["overview"]
            rating = metadata["rating"]
            
        if not poster and getattr(media, "thumbnail", None):
            poster = "telegram_thumbnail"
            
        movie = TelegramMovie.objects.create(
            title=title[:255],
            content_type="movie",
            category=channel.category,
            channel=channel,
            release_date=release_date,
            telegram_message_id=post.message_id,
            telegram_file_id=media.file_id,
            telegram_message_link=message_link,
            quality=extract_quality(caption),
            description=clean_caption(caption),
            
            # TMDB Metadata
            poster=poster,
            banner=banner,
            overview=overview,
            rating=rating,
            
            # Telegram media metadata
            file_size=(
                f"{round(media.file_size / (1024 ** 3), 2)} GB"
                if getattr(media, "file_size", None)
                and media.file_size >= (1024 ** 3)
                else (
                    f"{round(media.file_size / (1024 ** 2), 2)} MB"
                    if getattr(media, "file_size", None)
                    else ""
                )
            ),
            
            duration=(
                str(media.duration)
                if getattr(media, "duration", None)
                else ""
            ),
            )
        
        print("DATABASE ID:", movie.pk)
        print("TITLE:", movie.title)
        print("MESSAGE ID:", movie.telegram_message_id)
        print("POSTER:", poster)
        print("RATING:", rating)
        print("=" * 60)

        # Verify immediately after save
        exists = TelegramMovie.objects.filter(
            pk=movie.pk
        ).exists()

        print("EXISTS AFTER SAVE:", exists)

        if exists:
            verified_movie = TelegramMovie.objects.get(
                pk=movie.pk
            )

            print("=" * 60)
            print("DATABASE VERIFICATION SUCCESSFUL")
            print("VERIFIED ID:", verified_movie.pk)
            print("VERIFIED TITLE:", verified_movie.title)
            print(
                "VERIFIED MESSAGE ID:",
                verified_movie.telegram_message_id
            )
            print("=" * 60)
        else:
            print("=" * 60)
            print("WARNING: OBJECT NOT FOUND AFTER SAVE")
            print("=" * 60)

        return movie

    except Exception as e:
        print("=" * 60)
        print("DATABASE SAVE FAILED")
        print("ERROR TYPE:", type(e).__name__)
        print("ERROR:", str(e))
        traceback.print_exc()
        print("=" * 60)

        raise
        
async def handle_channel_post(update, context):
    print("=" * 60)
    print("CHANNEL HANDLER FIRED")

    # post = update.channel_post
    
    post = update.channel_post or update.message
    
    if not post:
        return

    if not post:
        print("NO CHANNEL POST")
        return

    print("CHAT ID:", post.chat.id)
    print("VIDEO:", bool(post.video))
    print("DOCUMENT:", bool(post.document))
    print("CAPTION:", post.caption)

    # Support both videos and MKV documents
    media = post.video or post.document

    if not media:
        print("NO VIDEO OR DOCUMENT FOUND")
        return

    if post.document:
        print(
            "DOCUMENT NAME:",
            getattr(post.document, "file_name", "Unknown")
        )

    if post.video:
        print("VIDEO RECEIVED")

    chat_id = str(post.chat.id)

    channel = await sync_to_async(
        lambda: TelegramChannel.objects.select_related(
            "category"
        ).filter(
            chat_id=chat_id
        ).first()
    )()

    if not channel:
        print(f"CHANNEL NOT FOUND: {chat_id}")
        return

    print("CHANNEL FOUND ID:", channel.id)
    print("CHANNEL FOUND NAME:", channel.name)
    print("CHANNEL CHAT ID:", channel.chat_id)

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

        print("✅ MOVIE SAVED SUCCESSFULLY")
        print("MESSAGE LINK:", message_link)

    except Exception as e:
        import traceback

        print("❌ SAVE ERROR:", str(e))
        traceback.print_exc()

    print("=" * 60)