# Create your views here.
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import F
from django.core.paginator import Paginator
import asyncio
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from django.http import HttpResponseForbidden
from .bot import get_application
from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from .forms import (
    TelegramMovieUploadForm,
    TelegramMovieEditForm,
    CustomUserCreationForm,
    CustomUserChangeForm,
    CategoryForm,
)

from .models import (
    Video,
    WatchList,
    Category,
    MembershipVerification,
    TelegramMovie,
    TelegramChannel,
)

from .services.telegram_upload import (
    upload_video_to_channel,
)

from .telegram_utils import (
    generate_verification_code,
)

from django.core.cache import cache

# coremovieshub/views.py (add at the bottom)
import json
from asgiref.sync import async_to_sync
from django.http import JsonResponse
import logging
from django.views.decorators.csrf import csrf_exempt
from telegram import Update

logger = logging.getLogger(__name__)

@login_required
def watch_movie(request, movie_id):

    movie = get_object_or_404(
        TelegramMovie,
        id=movie_id
    )

    verification, created = (
        MembershipVerification.objects.get_or_create(
            user=request.user
        )
    )

    if not verification.membership_status:
        messages.warning(
            request,
            "Please verify your Telegram account first."
        )

        return redirect(
            "verify_telegram"
        )

    return redirect(
        movie.telegram_message_link
    )

@login_required
def download_movie(request, movie_id):

    movie = get_object_or_404(
        TelegramMovie,
        id=movie_id
    )

    verification, created = (
        MembershipVerification.objects.get_or_create(
            user=request.user
        )
    )

    if not verification.membership_status:
        messages.warning(
            request,
            "Please verify your Telegram account first."
        )

        return redirect(
            "verify_telegram"
        )

    return redirect(
        movie.telegram_message_link
    )
        
@csrf_exempt
def telegram_webhook(request):
    """
    Telegram webhook endpoint.
    """

    logger.warning("🚀 WEBHOOK HIT")

    if request.method != "POST":
        logger.warning(
            "❌ Invalid method: %s",
            request.method
        )

        return JsonResponse(
            {"error": "Method not allowed"},
            status=405
        )

    secret_token = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    )

    logger.warning(
        "🔑 Received Secret: %s",
        secret_token
    )

    logger.warning(
        "🔑 Expected Secret: %s",
        settings.TELEGRAM_SECRET
    )

    if secret_token != settings.TELEGRAM_SECRET:
        logger.error(
            "❌ Secret token mismatch"
        )

        return JsonResponse(
            {"error": "Unauthorized"},
            status=403
        )

    try:
        data = json.loads(
            request.body.decode("utf-8")
        )

        logger.warning(
            "📩 Update received: %s",
            data
        )

        logger.warning(
            "⚙️ INITIALISING APPLICATION"
        )

        app = get_application()

        logger.warning(
            "✅ APPLICATION READY"
        )

        update = Update.de_json(
            data,
            app.bot
        )

        logger.warning(
            "🔄 PROCESSING UPDATE"
        )

        async_to_sync(
            app.process_update
        )(update)

        logger.warning(
            "✅ UPDATE PROCESSED SUCCESSFULLY"
        )

        return JsonResponse(
            {"status": "ok"}
        )

    except Exception as e:
        logger.exception(
            "❌ Webhook processing failed: %s",
            str(e)
        )

        return JsonResponse(
            {
                "error": "Internal server error",
                "details": str(e)
            },
            status=500
        )

@login_required
def my_watchlist(request):

    watchlist = (
        WatchList.objects
        .filter(user=request.user)
        .select_related(
            "movie",
            "movie__category"
        )
        .order_by("-added_at")
    )

    return render(
        request,
        "movies/watchlist.html",
        {
            "watchlist": watchlist
        }
    )
    
@login_required
def add_to_watchlist(
    request,
    movie_id
):

    movie = get_object_or_404(
        TelegramMovie,
        id=movie_id
    )

    WatchList.objects.get_or_create(
        user=request.user,
        movie=movie
    )

    messages.success(
        request,
        "Added to watchlist."
    )

    return redirect(
        "movie_detail",
        movie_id=movie.id
    )

@login_required
def remove_from_watchlist(
    request,
    movie_id
):

    WatchList.objects.filter(
        user=request.user,
        movie_id=movie_id
    ).delete()

    messages.success(
        request,
        "Removed from watchlist."
    )

    return redirect(
        "my_watchlist"
    )


@staff_member_required
def admin_dashboard(request):

    stats = {
        "total_movies": TelegramMovie.objects.count(),
        "total_categories": Category.objects.count(),
        "total_channels": TelegramChannel.objects.count(),
        "verified_users": MembershipVerification.objects.filter(
            membership_status=True
        ).count(),

        "latest_movies": TelegramMovie.objects.select_related(
            "category"
        ).order_by("-created_at")[:10],

        "top_movies": TelegramMovie.objects.order_by(
            "-views"
        )[:10],

        "unverified_users": MembershipVerification.objects.filter(
            membership_status=False
        ).count(),
    }

    return render(
        request,
        "dashboard/admin_dashboard.html",
        stats
    )
    
def verification_expired(verification):
    if not verification.verified_at:
        return True

    return (
        timezone.now() - verification.verified_at
    ) > timedelta(days=7)

@staff_member_required
def movie_management(request):

    movies = (
        TelegramMovie.objects
        .select_related("category", "channel")
        .order_by("-created_at")
    )

    paginator = Paginator(movies, 25)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "admin/movie_management.html",
        {
            "movies": page_obj,
            "page_obj": page_obj,
        }
    )
    
@staff_member_required
def edit_movie(request, movie_id):

    movie = get_object_or_404(
        TelegramMovie,
        id=movie_id
    )

    if request.method == "POST":

        form = TelegramMovieEditForm(
            request.POST,
            request.FILES,
            instance=movie
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Movie updated successfully."
            )

            return redirect(
                "movie_management"
            )

    else:

        form = TelegramMovieEditForm(
            instance=movie
        )

    return render(
        request,
        "admin/edit_movie.html",
        {
            "form": form,
            "movie": movie
        }
    )
    
@staff_member_required
def delete_movie(request, movie_id):

    movie = get_object_or_404(
        TelegramMovie,
        id=movie_id
    )

    if request.method == "POST":

        if movie.poster:
            movie.poster.delete(
                save=False
            )

        movie.delete()

        messages.success(
            request,
            "Movie deleted successfully."
        )

        return redirect(
            "movie_management"
        )

    return render(
        request,
        "admin/delete_movie.html",
        {
            "movie": movie
        }
    )
    
@login_required
def movie_detail(request, movie_id):
    movie = get_object_or_404(
        TelegramMovie,
        id=movie_id
    )

    # Get user's verification status
    verification, created = (
        MembershipVerification.objects.get_or_create(
            user=request.user
        )
    )

    # Force re-verification every 7 days
    if (
        not verification.membership_status
        or verification_expired(
            verification
        )
    ):
        messages.warning(
            request,
            "Please verify Telegram again."
        )

        return redirect(
            "verify_telegram"
        )

    # Increment view count atomically
    TelegramMovie.objects.filter(
        id=movie.id
    ).update(
        views=F("views") + 1
    )

    movie.refresh_from_db()

    return render(
        request,
        "movies/movie_detail.html",
        {
            "movie": movie,
            "is_verified": verification.membership_status,
        }
    )
        
@login_required
def category_movies(request, slug):

    category = get_object_or_404(
        Category,
        slug=slug
    )

    movies = (
        TelegramMovie.objects
        .filter(category=category)
        .select_related("category", "channel")
        .order_by("-created_at")
    )

    paginator = Paginator(movies, 24)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "movies/category_movies.html",
        {
            "category": category,
            "movies": page_obj,
            "page_obj": page_obj,
        }
    )
    
@login_required
def search_movies(request):

    query = request.GET.get("q", "")

    movies = TelegramMovie.objects.none()

    if query:

        search_filter = (
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(language__icontains=query) |
            Q(quality__icontains=query) |
            Q(tags__icontains=query) |
            Q(content_type__icontains=query) |
            Q(status__icontains=query) |
            Q(category__name__icontains=query)
        )

        if query.isdigit():
            search_filter |= Q(year=int(query))

        movies = (
            TelegramMovie.objects
            .select_related(
                "category",
                "channel"
            )
            .filter(search_filter)
            .distinct()
            .order_by("-created_at")
        )

    paginator = Paginator(movies, 24)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "movies/search_results.html",
        {
            "query": query,
            "movies": page_obj,
            "page_obj": page_obj,
        }
    )

def home(request):
    latest_movies = (
        TelegramMovie.objects
        .select_related("category", "channel")
        .order_by("-created_at")[:12]
    )

    featured_movies = (
        TelegramMovie.objects
        .select_related("category", "channel")
        .filter(is_featured=True)[:8]
    )

    categories = Category.objects.all()

    return render(
        request,
        "home/home.html",
        {
            "latest_movies": latest_movies,
            "featured_movies": featured_movies,
            "categories": categories,
        }
    )
    
def about(request):
    return render(request, 'home/about.html')

def contact(request):
    return render(request, 'home/contact.html')

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('home')
    else:
        form = CustomUserCreationForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile(request):
    return render(request, 'accounts/profile.html')


@login_required
def edit_profile(request):
    if request.method == 'POST':
        form = CustomUserChangeForm(
            request.POST,
            instance=request.user
        )

        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')

    else:
        form = CustomUserChangeForm(instance=request.user)

    return render(
        request,
        'accounts/edit_profile.html',
        {'form': form}
    )

@login_required
def video_list(request):

    verification = get_object_or_404(
        MembershipVerification,
        user=request.user
    )

    if (
        not verification.membership_status
        or verification_expired(
            verification
            )
        ):

        messages.warning(
            request,
            "You must verify your Telegram membership to watch videos."
        )

        return redirect(
            "verify_telegram"
        )

    movies = (
        TelegramMovie.objects
        .select_related(
            "category",
            "channel"
        )
        .order_by("-created_at")
    )

    paginator = Paginator(movies, 24)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "videos/video_list.html",
        {
            "movies": page_obj,
            "page_obj": page_obj,
        }
    )

@staff_member_required
def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Category "{form.cleaned_data["name"]}" added successfully!')
            return redirect('add_category')  # stay on same page to add more
    else:
        form = CategoryForm()
    
    categories = Category.objects.all().order_by('name')
    return render(request, 'categories/add_category.html', {'form': form, 'categories': categories})


@login_required
def verify_telegram(request):
    verification, created = MembershipVerification.objects.get_or_create(user=request.user)
    
    if verification.membership_status:
        messages.info(request, 'You are already verified!')
        return redirect('video_list')
    
    code = generate_verification_code(request.user)
    bot_username = settings.TELEGRAM_BOT_USERNAME
    telegram_deep_link = f"https://t.me/{bot_username}?start=verify_{code}"
    
    return render(request, 'telegram/verify.html', {
        'telegram_deep_link': telegram_deep_link,
        'channel_link': settings.MAIN_CHANNEL_ID,
        'is_verified': verification.membership_status,
    })
    
@login_required
def check_verification(request):
    verification, created = MembershipVerification.objects.get_or_create(user=request.user)
    # If already verified, redirect to videos
    if verification.membership_status:
        messages.success(request, 'You are already verified! Enjoy the videos.')
        return redirect('video_list')
    
    # For AJAX polling (optional)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'verified': verification.membership_status})
    
    # # For manual check
    # return render(request, 'telegram/check_status.html', {'verified': verification.membership_status})
     
    # For manual check – just redirect back to verification page
    messages.warning(request, 'You are not verified yet. Please join the Telegram channel and verify.')
    return redirect('verify_telegram')

@staff_member_required
def upload_movie(request):
    if request.method == "POST":
        form = TelegramMovieUploadForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            category = form.cleaned_data["category"]

            try:
                channel = TelegramChannel.objects.get(
                    category=category
                )

            except TelegramChannel.DoesNotExist:
                messages.error(
                    request,
                    f"No Telegram channel configured for category '{category.name}'."
                )
                return redirect("upload_movie")

            caption = (
                f"{form.cleaned_data['title']}\n"
                f"Year: {form.cleaned_data.get('year', 'N/A')}\n"
                f"Quality: {form.cleaned_data.get('quality', 'N/A')}"
            )
            
            # Upload video to Telegram
            try:
                sent_message = async_to_sync(
                    upload_video_to_channel
                )(
                    file_obj=request.FILES["movie_file"],
                    chat_id=channel.chat_id,
                    caption=caption
                )

            except Exception as e:
                logger.exception(
                    "Telegram upload failed"
                )

                messages.error(
                    request,
                    f"Telegram upload failed: {str(e)}"
                )

                return redirect("upload_movie")

            movie = form.save(commit=False)

            movie.channel = channel
            movie.telegram_message_id = sent_message.message_id

            if sent_message.video:
                movie.telegram_file_id = (
                    sent_message.video.file_id
                )

            chat_link_part = str(channel.chat_id)

            if chat_link_part.startswith("-100"):
                chat_link_part = chat_link_part[4:]

            movie.telegram_message_link = (
                f"https://t.me/c/"
                f"{chat_link_part}/"
                f"{sent_message.message_id}"
            )

            movie.save()

            messages.success(
                request,
                f"Movie '{movie.title}' uploaded successfully!"
            )

            return redirect("admin_dashboard")

    else:
        form = TelegramMovieUploadForm()

    return render(
        request,
        "admin/upload_movie.html",
        {
            "form": form
        }
    )    
