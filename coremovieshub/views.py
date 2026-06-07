# Create your views here.
from .forms import TelegramMovieUploadForm
from .services.telegram_upload import upload_video_to_channel
import asyncio
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Video
from .forms import CustomUserCreationForm, CustomUserChangeForm
from django.contrib.admin.views.decorators import staff_member_required
from .forms import CategoryForm
from .models import Category
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .models import MembershipVerification
from .telegram_utils import generate_verification_code
from django.http import JsonResponse
from .telegram_utils import check_telegram_membership
from django.conf import settings
from .models import TelegramMovie
from django.db.models import Count
from .models import (
    TelegramMovie,
    TelegramChannel,
    MembershipVerification,
    Category
)

@staff_member_required
def admin_dashboard(request):

    total_movies = TelegramMovie.objects.count()

    total_categories = Category.objects.count()

    total_channels = TelegramChannel.objects.count()

    verified_users = MembershipVerification.objects.filter(
        membership_status=True
    ).count()

    context = {
        "total_movies": total_movies,
        "total_categories": total_categories,
        "total_channels": total_channels,
        "verified_users": verified_users,
    }

    return render(
        request,
        "dashboard/admin_dashboard.html",
        context
    )
    
@login_required
def movie_detail(request, movie_id):

    movie = get_object_or_404(
        TelegramMovie,
        id=movie_id
    )

    movie.views += 1
    movie.save()

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
        movies = TelegramMovie.objects.filter(
            title__icontains=query
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

    latest_movies = TelegramMovie.objects.order_by(
        "-created_at"
    )[:12]

    featured_movies = TelegramMovie.objects.filter(
        is_featured=True
    )[:8]

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
    
from .models import TelegramMovie   # add at the top

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
    verification = get_object_or_404(MembershipVerification, user=request.user)
    
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
    if request.method == 'POST':
        form = TelegramMovieUploadForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            category = form.cleaned_data['category']

            try:
                channel = TelegramChannel.objects.get(
                    category=category
                )

            except TelegramChannel.DoesNotExist:
                messages.error(
                    request,
                    f"No Telegram channel configured for category '{category.name}'"
                )
                return redirect('upload_movie')

            caption = (
                f"{form.cleaned_data['title']}\n"
                f"Year: {form.cleaned_data.get('year', 'N/A')}\n"
                f"Quality: {form.cleaned_data.get('quality', 'N/A')}"
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                sent_message = loop.run_until_complete(
                    upload_video_to_channel(
                        file_obj=request.FILES['movie_file'],
                        chat_id=channel.chat_id,
                        caption=caption
                    )
                )
            finally:
                loop.close()

            movie = form.save(commit=False)

            movie.channel = channel
            movie.telegram_message_id = sent_message.message_id
            movie.telegram_file_id = sent_message.video.file_id

            chat_link_part = str(channel.chat_id)

            if chat_link_part.startswith("-100"):
                chat_link_part = chat_link_part[4:]

            movie.telegram_message_link = (
                f"https://t.me/c/{chat_link_part}/{sent_message.message_id}"
            )

            movie.save()

            messages.success(
                request,
                f"Movie '{movie.title}' uploaded successfully!"
            )

            return redirect('admin_dashboard')

    else:
        form = TelegramMovieUploadForm()

    return render(
        request,
        'admin/upload_movie.html',
        {
            'form': form
        }
    )
    
