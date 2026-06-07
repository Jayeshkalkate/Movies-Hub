# Create your views here.
import logging

from asgiref.sync import async_to_sync

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import F
import asyncio
from django.http import JsonResponse
from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)

from .forms import (
    TelegramMovieUploadForm,
    CustomUserCreationForm,
    CustomUserChangeForm,
    CategoryForm,
)

from .models import (
    Video,
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

logger = logging.getLogger(__name__)

from django.core.cache import cache

# coremovieshub/views.py (add at the bottom)
import json
from asgiref.sync import async_to_sync
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from telegram import Update
from .bot import setup_bot

from telegram.ext import Application, ExtBot
from telegram import Update
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .bot import setup_bot  # we'll modify this to return the app


import json
import asyncio
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from telegram import Update

logger = logging.getLogger(__name__)

_bot_app = None

def get_bot_app():
    global _bot_app
    if _bot_app is None:
        _bot_app = setup_bot()
    return _bot_app

@csrf_exempt
def telegram_webhook(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Method not allowed"},
            status=405
        )

    # Verify Telegram secret token
    secret_token = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    )

    if secret_token != settings.TELEGRAM_SECRET:
        logger.warning(
            "Unauthorized webhook request received."
        )
        return JsonResponse(
            {"error": "Unauthorized"},
            status=403
        )

    try:
        data = json.loads(request.body)

        app = get_bot_app()

        update = Update.de_json(
            data,
            app.bot
        )

        # Run async update processor
        asyncio.run(
            app.process_update(update)
        )

        return JsonResponse(
            {"status": "ok"}
        )

    except json.JSONDecodeError:
        logger.exception(
            "Invalid JSON received from webhook."
        )
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400
        )

    except Exception as e:
        logger.exception(
            "Webhook processing failed."
        )
        return JsonResponse(
            {"error": str(e)},
            status=500
        )
        
@staff_member_required
def admin_dashboard(request):

    stats = cache.get("admin_dashboard_stats")

    if not stats:
        stats = {
            "total_movies": TelegramMovie.objects.count(),
            "total_categories": Category.objects.count(),
            "total_channels": TelegramChannel.objects.count(),
            "verified_users": MembershipVerification.objects.filter(
                membership_status=True
            ).count(),
        }

        # Cache for 5 minutes
        cache.set(
            "admin_dashboard_stats",
            stats,
            timeout=300
        )

    return render(
        request,
        "dashboard/admin_dashboard.html",
        stats
    )

@login_required
def movie_detail(request, movie_id):
    movie = get_object_or_404(
        TelegramMovie,
        id=movie_id
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
            "movie": movie
        }
    )
    
@login_required
def category_movies(request, slug):

    category = get_object_or_404(
        Category,
        slug=slug
    )

    movies = TelegramMovie.objects.filter(
        category=category
    )

    return render(
        request,
        "movies/category_movies.html",
        {
            "category": category,
            "movies": movies
        }
    )
    
@login_required
def search_movies(request):
    query = request.GET.get("q", "")
    
    movies = TelegramMovie.objects.none()

    if query:
        movies = (
            TelegramMovie.objects
            .select_related("category", "channel")
            .filter(title__icontains=query)
        ).select_related(
            "category",
            "channel"
        )

    return render(
        request,
        "movies/search_results.html",
        {
            "query": query,
            "movies": movies
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
    # Redirect to verification page if not verified
    verification = get_object_or_404(MembershipVerification, user=request.user)
    if not verification.membership_status:
        messages.warning(request, 'You must verify your Telegram membership to watch videos.')
        return redirect('verify_telegram')

    # Show Telegram movies (indexed from channels)
    movies = TelegramMovie.objects.select_related('category', 'channel').all().order_by('-created_at')
    return render(request, 'videos/video_list.html', {'movies': movies})

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

import logging

logger = logging.getLogger(__name__)


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
