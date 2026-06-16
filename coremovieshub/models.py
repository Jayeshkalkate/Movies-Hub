from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


# =====================================================
# CUSTOM USER
# =====================================================

class CustomUser(AbstractUser):
    def __str__(self):
        return self.username


# =====================================================
# CATEGORY
# =====================================================

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Emoji icon"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# =====================================================
# WEBSITE VIDEOS
# =====================================================

class Video(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to="thumbnails/")
    video_file = models.FileField(upload_to="videos/")

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title
    
# =====================================================
# TELEGRAM MEMBERSHIP VERIFICATION
# =====================================================

class MembershipVerification(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE
    )

    telegram_id = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )
    
    telegram_username = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    membership_status = models.BooleanField(default=False)

    verification_code = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        null=True
    )

    verified_at = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {'Verified' if self.membership_status else 'Not Verified'}"


# =====================================================
# TELEGRAM CHANNELS
# =====================================================

class TelegramChannel(models.Model):
    name = models.CharField(max_length=100, unique=True)

    chat_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Telegram Channel ID (Example: -1001234567890)"
    )

    category = models.OneToOneField(
        Category,
        on_delete=models.CASCADE,
        related_name="telegram_channel"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.category.name})"


# =====================================================
# TMBD MOVIE
# =====================================================

class TMDBMovie(models.Model):
    title = models.CharField(
        max_length=500,
        db_index=True,
    )

    title_normalized = models.CharField(
        max_length=500,
        unique=True,
        blank=True,
    )
    
    tmdb_id = models.IntegerField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    
    runtime = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    
    status = models.CharField(
        max_length=50,
        blank=True,
    )
    
    number_of_seasons = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    
    number_of_episodes = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    
    backdrop_path = models.TextField(
        blank=True,
    )

    poster_path = models.TextField(
        blank=True,
    )

    overview = models.TextField(
        blank=True,
    )

    genres = models.TextField(
        blank=True,
    )

    release_date = models.DateField(
        null=True,
        blank=True,
    )

    vote_average = models.FloatField(
        null=True,
        blank=True,
    )
    
    def __str__(self):
        return self.title

    class Meta:
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["title_normalized"]),
            models.Index(fields=["release_date"]),
            models.Index(fields=["vote_average"]),
        ]
    
# =====================================================
# TELEGRAM MOVIES
# =====================================================

class TelegramMovie(models.Model):

    CONTENT_TYPES = (
        ("movie", "Movie"),
        ("series", "Series"),
        ("anime", "Anime"),
        ("documentary", "Documentary"),
        ("tvshow", "TV Show"),
    )

    STATUS_CHOICES = (
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
        ("upcoming", "Upcoming"),
    )

    title = models.CharField(max_length=300)

    slug = models.SlugField(
        max_length=300,
        unique=True,
        blank=True,
        db_index=True,
    )

    content_type = models.CharField(
        max_length=20,
        choices=CONTENT_TYPES,
        default="movie",
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    channel = models.ForeignKey(
        TelegramChannel,
        on_delete=models.CASCADE,
        related_name="movies",
    )

    # Telegram Details
    telegram_message_id = models.BigIntegerField(
        blank=True,
        null=True,
    )

    telegram_file_id = models.TextField(
        blank=True,
        null=True,
    )

    telegram_message_link = models.URLField(
        blank=True,
        null=True,
    )

    # Movie Information
    year = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    release_date = models.DateField(
        null=True,
        blank=True,
    )

    quality = models.CharField(
        max_length=20,
        blank=True,
    )

    language = models.CharField(
        max_length=50,
        blank=True,
    )

    duration = models.CharField(
        max_length=30,
        blank=True,
    )

    # TMDB Information
    poster = models.URLField(
        blank=True,
        null=True,
    )

    banner = models.URLField(
        blank=True,
        null=True,
    )

    tmdb_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
    )

    season_count = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    
    episode_count = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    overview = models.TextField(
        blank=True,
        default="",
    )

    rating = models.FloatField(
        null=True,
        blank=True,
    )

    description = models.TextField(
        blank=True,
        default="",
        help_text="Telegram caption or custom notes",
    )

    file_size = models.CharField(
        max_length=30,
        blank=True,
    )
    
    file_size_bytes = models.BigIntegerField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="completed",
    )

    # Series Information
    season = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    episode = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    # Search Tags
    tags = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma separated tags",
    )

    # Statistics
    views = models.PositiveIntegerField(default=0)

    downloads = models.PositiveIntegerField(default=0)

    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

        verbose_name = "Telegram Movie"
        verbose_name_plural = "Telegram Movies"

        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["year"]),
            models.Index(fields=["quality"]),
            models.Index(fields=["language"]),
            models.Index(fields=["content_type"]),
            models.Index(fields=["is_featured"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["slug"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "telegram_message_id",
                    "channel",
                ],
                condition=models.Q(
                        telegram_message_id__isnull=False
                ),
                name="unique_channel_message",
            )
        ]

    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:90] or "movie"
            
            slug = base_slug
            counter = 1
            
            while TelegramMovie.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():
                
                slug = f"{base_slug}-{counter}"
                counter += 1
                
            self.slug = slug
                
        super().save(*args, **kwargs)
                

    @property
    def can_download_from_website(self):
        
        if self.file_size_bytes is None:
            return False
            
        return self.file_size_bytes <= (
                2 * 1024 * 1024 * 1024
        )


# =====================================================
# USER WATCHLIST
# =====================================================

class WatchList(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE
    )

    movie = models.ForeignKey(
        TelegramMovie,
        on_delete=models.CASCADE
    )

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "movie"],
                name="unique_watchlist",
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.movie.title}"


# =====================================================
# DOWNLOAD HISTORY
# =====================================================

class DownloadHistory(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE
    )

    movie = models.ForeignKey(
        TelegramMovie,
        on_delete=models.CASCADE
    )

    downloaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} downloaded {self.movie.title}"
    
    class Meta:
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["movie"]),
            models.Index(fields=["downloaded_at"]),
        ]
    
