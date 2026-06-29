# handlers.py
"""
Telegram bot handlers for MoviesHub.

Handles:
- /start with deep‑link verification
- Membership verification (async)
- Movie upload conversation (admin only)
- /search command
- Automatic channel post processing with full metadata enrichment
"""

import logging
import re
from typing import Optional, List, Dict, Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

# ---------------------------------------------------------------------
# Import project models and utilities
# ---------------------------------------------------------------------
from coremovieshub.models import (
    MembershipVerification,
    Category,
    TelegramChannel,
    TelegramMovie,
)
from coremovieshub.telegram_utils import check_telegram_membership

# Import the metadata manager (assumed to be at metadata.manager)
# If not available, fallback to a dummy manager.
try:
    from metadata.manager import get_manager
except ImportError:
    # Fallback: define a dummy manager that returns None
    def get_manager():
        class DummyManager:
            def process_caption(self, caption, filename=None, telegram_file_id=None):
                return None
        return DummyManager()

# Import movie_parser utilities – fallback to simple regex if missing.
try:
    from coremovieshub.utils.movie_parser import (
        clean_caption,
        extract_title,
        extract_quality,
        extract_languages,
        extract_season,
        extract_year,
    )
except ImportError:
    # Fallback implementations
    def clean_caption(text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()

    def extract_title(text: str) -> Optional[str]:
        # Simple: take first few words or use regex
        # In production, use proper parser
        return text.split('\n')[0].strip()

    def extract_quality(text: str) -> Optional[str]:
        match = re.search(r'\b(480p|720p|1080p|4K|2160p)\b', text, re.I)
        return match.group(1).upper() if match else None

    def extract_languages(text: str) -> List[str]:
        # Simple: look for language names
        langs = []
        for lang in ['Hindi', 'English', 'Tamil', 'Telugu', 'Malayalam', 'Kannada']:
            if re.search(rf'\b{lang}\b', text, re.I):
                langs.append(lang)
        return langs

    def extract_season(text: str) -> Optional[int]:
        match = re.search(r'\bS(\d{1,2})\b', text, re.I)
        return int(match.group(1)) if match else None

    def extract_year(text: str) -> Optional[int]:
        match = re.search(r'\b(19|20)\d{2}\b', text)
        return int(match.group()) if match else None

logger = logging.getLogger(__name__)

# ------------------- Constants -------------------
REQUIRED_CHANNELS = [settings.MAIN_CHANNEL_ID]
ADMIN_IDS = {
    int(x) for x in getattr(settings, "TELEGRAM_ADMIN_IDS", [])
    if str(x).strip()
}
UPLOAD_STATES = range(5)  # TITLE, CATEGORY_STATE, YEAR, QUALITY, UPLOAD
TITLE, CATEGORY_STATE, YEAR, QUALITY, UPLOAD = UPLOAD_STATES


# ------------------- Helper Functions -------------------

def user_has_admin_access(user_id: int) -> bool:
    """Check if the user is in the admin list."""
    return user_id in ADMIN_IDS


# ------------------- Database Helpers (async) -------------------

@sync_to_async
def get_categories() -> List[Category]:
    return list(Category.objects.order_by("name"))


@sync_to_async
def get_category(category_id: int) -> Optional[Category]:
    return Category.objects.filter(id=category_id).first()


@sync_to_async
def get_channel_for_category(category: Category) -> Optional[TelegramChannel]:
    return TelegramChannel.objects.filter(category=category).first()


@sync_to_async
def save_movie_record(**kwargs) -> TelegramMovie:
    return TelegramMovie.objects.create(**kwargs)


@sync_to_async
def get_or_create_verification(telegram_id: int):
    return MembershipVerification.objects.get_or_create(
        telegram_id=str(telegram_id),
        defaults={"membership_status": False},
    )


@sync_to_async
def get_verification_by_code(code: str) -> Optional[MembershipVerification]:
    return MembershipVerification.objects.filter(verification_code=code).first()


@sync_to_async
def get_movies_by_title(query: str) -> List[TelegramMovie]:
    return list(
        TelegramMovie.objects.filter(title__icontains=query)
        .select_related("category", "channel")
        .order_by("-created_at")[:10]
    )


@sync_to_async
def get_channel_by_chat_id(chat_id: str) -> Optional[TelegramChannel]:
    return TelegramChannel.objects.select_related("category").filter(chat_id=chat_id).first()


# ------------------- Membership Verification -------------------

async def verify_membership(telegram_id: int, verification_code: str = None) -> str:
    """
    Verify a user's membership status.

    Returns:
        'verified', 'not_member', 'invalid_code', 'error'
    """
    try:
        if verification_code:
            verification = await get_verification_by_code(verification_code)
            if not verification:
                return "invalid_code"

            verification.telegram_id = str(telegram_id)
            # Optionally store username if available
            await sync_to_async(verification.save)()

            all_joined = all(
                await check_telegram_membership(telegram_id, ch)
                for ch in REQUIRED_CHANNELS
            )
            if all_joined:
                verification.membership_status = True
                verification.verified_at = timezone.now()
                await sync_to_async(verification.save)()
                return "verified"
            return "not_member"

        # Regular verification via stored telegram_id
        verification, created = await get_or_create_verification(telegram_id)
        if not verification:
            return "verification_not_found"

        all_joined = all(
            await check_telegram_membership(telegram_id, ch)
            for ch in REQUIRED_CHANNELS
        )
        if all_joined:
            verification.membership_status = True
            verification.verified_at = timezone.now()
            await sync_to_async(verification.save)()
            return "verified"
        return "not_member"

    except Exception:
        logger.exception("Membership verification failed for user %s", telegram_id)
        return "error"


# ------------------- /start Command -------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with optional deep‑link verification."""
    user = update.effective_user
    if not user:
        return

    telegram_id = user.id
    raw_code = context.args[0].strip() if context.args else None
    verification_code = None

    if raw_code and raw_code.startswith("verify_"):
        verification_code = raw_code.replace("verify_", "", 1).strip()
        logger.info("Verification code extracted: %s", verification_code)

    # No parameter → welcome message
    if not raw_code:
        keyboard = [[InlineKeyboardButton("🌐 Open Website", url=settings.BASE_URL)]]
        await update.message.reply_text(
            "🎬 Welcome to MoviesHub!\n\n"
            "To access movies:\n"
            "1️⃣ Register on website\n"
            "2️⃣ Login\n"
            "3️⃣ Verify Telegram\n"
            "4️⃣ Join required channels\n"
            "5️⃣ Start watching movies",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # Invalid code format
    if verification_code is None:
        await update.message.reply_text(
            "⚠️ Invalid verification link.\n\n"
            "Please return to MoviesHub and generate a new verification link."
        )
        return

    # Perform verification
    result = await verify_membership(telegram_id, verification_code)
    logger.info("Verification result for %s: %s", telegram_id, result)

    messages = {
        "verified": (
            "✅ Account verified successfully!\n\n"
            "You can now return to MoviesHub and continue.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("🎬 Open MoviesHub", url=settings.BASE_URL)]]
            ),
        ),
        "not_member": (
            "❌ Verification failed.\n\n"
            "Please join the required Telegram channel and try again.",
            None,
        ),
        "invalid_code": (
            "⚠️ Invalid or expired verification link.\n\n"
            "Please generate a new one.",
            None,
        ),
        "verification_not_found": (
            "⚠️ Verification record not found.",
            None,
        ),
        "error": (
            "⚠️ Verification could not be completed.\n\n"
            "Please try again later.",
            None,
        ),
    }
    text, reply_markup = messages.get(result, ("⚠️ Unexpected error.", None))
    await update.message.reply_text(text, reply_markup=reply_markup)


# ------------------- Movie Upload Conversation -------------------

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the movie upload conversation (admin only)."""
    if not user_has_admin_access(update.effective_user.id):
        await update.message.reply_text("❌ Only administrators can upload movies.")
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text("🎬 Enter movie title:")
    return TITLE


async def title_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store title and ask for category."""
    context.user_data["title"] = update.message.text.strip()
    categories = await get_categories()
    if not categories:
        await update.message.reply_text("❌ No categories found.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(cat.name, callback_data=str(cat.id))]
        for cat in categories
    ]
    await update.message.reply_text(
        "📂 Choose category:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CATEGORY_STATE


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store category ID and ask for year."""
    query = update.callback_query
    await query.answer()
    context.user_data["category_id"] = int(query.data)
    await query.edit_message_text("📅 Enter release year (e.g., 2024):")
    return YEAR


async def year_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store year (validate) and ask for quality."""
    year_text = update.message.text.strip()
    try:
        year = int(year_text)
        if 1900 <= year <= timezone.now().year + 1:
            context.user_data["year"] = year
        else:
            context.user_data["year"] = None
            await update.message.reply_text("⚠️ Invalid year. Using 'N/A'.")
    except ValueError:
        context.user_data["year"] = None
        await update.message.reply_text("⚠️ Invalid year. Using 'N/A'.")

    await update.message.reply_text("🎥 Enter quality (480p / 720p / 1080p / 4K):")
    return QUALITY


async def quality_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store quality and ask for file."""
    context.user_data["quality"] = update.message.text.strip()
    await update.message.reply_text("📤 Send the movie file now.")
    return UPLOAD


async def video_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process uploaded video/document and save to channel & DB."""
    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("❌ Please send a video or document file.")
        return UPLOAD

    category = await get_category(context.user_data["category_id"])
    if not category:
        await update.message.reply_text("❌ Category not found.")
        return ConversationHandler.END

    channel = await get_channel_for_category(category)
    if not channel:
        await update.message.reply_text("❌ No Telegram channel configured for this category.")
        return ConversationHandler.END

    await update.message.reply_text("⏳ Uploading movie...")

    caption = (
        f"🎬 {context.user_data['title']}\n"
        f"📅 Year: {context.user_data.get('year', 'N/A')}\n"
        f"🎥 Quality: {context.user_data['quality']}"
    )

    try:
        if update.message.video:
            sent = await context.bot.send_video(
                chat_id=channel.chat_id,
                video=video.file_id,
                caption=caption,
                supports_streaming=True,
            )
        else:
            sent = await context.bot.send_document(
                chat_id=channel.chat_id,
                document=video.file_id,
                caption=caption,
            )
    except Exception as e:
        logger.error("Failed to send media to channel: %s", e)
        await update.message.reply_text("❌ Failed to upload movie. Please try again.")
        return ConversationHandler.END

    # Build message link
    chat_id_str = str(channel.chat_id)
    if chat_id_str.startswith("-100"):
        chat_id_str = chat_id_str[4:]
    message_link = f"https://t.me/c/{chat_id_str}/{sent.message_id}"

    # Save to database
    await save_movie_record(
        title=context.user_data["title"],
        category=category,
        channel=channel,
        telegram_message_id=sent.message_id,
        telegram_file_id=video.file_id,
        telegram_message_link=message_link,
        year=context.user_data.get("year"),
        quality=context.user_data["quality"],
        description=caption,
        language=", ".join(extract_languages(caption)) if extract_languages(caption) else "",
        season=extract_season(caption),
    )

    await update.message.reply_text(
        f"✅ Movie uploaded successfully!\n\n🎬 {context.user_data['title']}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel upload conversation."""
    context.user_data.clear()
    await update.message.reply_text("❌ Upload cancelled.")
    return ConversationHandler.END


# ------------------- /search Command -------------------

async def search_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for movies by title."""
    if not context.args:
        await update.message.reply_text("Usage:\n/search movie_name")
        return

    query = " ".join(context.args).strip()
    movies = await get_movies_by_title(query)

    if not movies:
        await update.message.reply_text("❌ No movies found.")
        return

    for movie in movies:
        category = movie.category.name if movie.category else "Unknown"
        year = movie.year or "N/A"
        quality = movie.quality or "N/A"
        link = movie.telegram_message_link or (
            f"https://t.me/c/{str(movie.channel.chat_id)[4:]}/{movie.telegram_message_id}"
            if movie.channel and movie.telegram_message_id else "#"
        )

        text = (
            f"🎬 *{movie.title}*\n"
            f"📂 Category: {category}\n"
            f"📅 Year: {year}\n"
            f"🎥 Quality: {quality}\n\n"
            f"🔗 [Watch on Telegram]({link})"
        )
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )


# ------------------- Channel Post Handler -------------------

@sync_to_async
def save_channel_movie(post, channel, media) -> Optional[TelegramMovie]:
    """
    Process a channel post and save movie metadata.
    Uses the metadata manager for full enrichment.
    """
    caption = post.caption or ""

    # Extract basic info from caption
    title = extract_title(caption) or "Untitled Movie"
    year = extract_year(caption)
    quality = extract_quality(caption)
    description = clean_caption(caption)
    languages = extract_languages(caption)

    # Build message link
    chat_id = str(channel.chat_id)
    if chat_id.startswith("-100"):
        chat_id = chat_id[4:]
    message_link = f"https://t.me/c/{chat_id}/{post.message_id}"

    # Prepare search text from filename and caption
    filename = ""
    if hasattr(post, "document") and post.document:
        filename = post.document.file_name or ""
    elif hasattr(post, "video") and post.video:
        filename = getattr(post.video, "file_name", "") or ""

    search_text = "\n".join(
        x.strip() for x in [filename, caption] if x and x.strip()
    )

    # Use the metadata manager to get enriched data
    manager = get_manager()
    try:
        metadata = manager.process_caption(search_text)
        logger.info("Metadata enrichment: %s", metadata)
    except Exception as e:
        logger.exception("Metadata manager failed: %s", e)
        metadata = None

    # Prepare defaults for the movie record
    if metadata:
        # Extract fields from metadata dict
        enriched_title = metadata.get("title")
        if enriched_title:
            title = enriched_title

        poster = metadata.get("poster") or metadata.get("poster_url")
        banner = metadata.get("backdrop") or metadata.get("backdrop_url") or poster
        overview = metadata.get("overview") or description
        rating = metadata.get("rating") or metadata.get("vote_average")
        release_date = metadata.get("release_date")
        tmdb_id = metadata.get("external_id")
        runtime = metadata.get("runtime")
    else:
        poster = None
        banner = None
        overview = description
        rating = None
        release_date = None
        tmdb_id = None
        runtime = None

    # Compute file size string
    file_size_bytes = getattr(media, "file_size", None)
    if file_size_bytes:
        if file_size_bytes >= 1024 ** 3:
            file_size = f"{round(file_size_bytes / (1024 ** 3), 2)} GB"
        else:
            file_size = f"{round(file_size_bytes / (1024 ** 2), 2)} MB"
    else:
        file_size = ""

    # Duration
    duration = runtime if runtime else getattr(media, "duration", None)
    if duration:
        duration = str(duration)

    defaults = {
        "title": title[:255],
        "content_type": "movie",
        "category": channel.category,
        "release_date": release_date,
        "year": year,
        "telegram_file_id": media.file_id,
        "telegram_message_link": message_link,
        "quality": quality,
        "description": description,
        "poster": poster,
        "banner": banner,
        "overview": overview,
        "rating": rating,
        "tmdb_id": tmdb_id,
        "file_size": file_size,
        "duration": duration,
        "language": ", ".join(languages) if languages else "",
    }

    # Get or create the movie record
    movie, created = TelegramMovie.objects.get_or_create(
        telegram_message_id=post.message_id,
        channel=channel,
        defaults=defaults,
    )

    if not created:
        # Update existing record with new data if needed
        for key, value in defaults.items():
            setattr(movie, key, value)
        movie.save()
        logger.info("Movie updated: %s", movie.title)
    else:
        logger.info("Movie saved: %s (ID %s)", movie.title, movie.pk)

    return movie


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new posts in configured channels."""
    logger.info("Channel post handler triggered.")
    post = update.channel_post or update.message
    if not post:
        return

    media = post.video or post.document
    if not media:
        logger.info("No media found in post.")
        return

    chat_id = str(post.chat.id)
    channel = await get_channel_by_chat_id(chat_id)
    if not channel:
        logger.warning("Channel not found: %s", chat_id)
        return

    try:
        await save_channel_movie(post, channel, media)
        logger.info("Movie saved successfully.")
    except Exception:
        logger.exception("Failed to save channel movie.")
        
