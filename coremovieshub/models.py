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
        blank=True
    )

    content_type = models.CharField(
        max_length=20,
        choices=CONTENT_TYPES,
        default="movie"
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    channel = models.ForeignKey(
        TelegramChannel,
        on_delete=models.CASCADE,
        related_name="movies"
    )

    # Telegram Details    
    telegram_message_id = models.BigIntegerField(
    blank=True,
    null=True
    )
    
    telegram_file_id = models.TextField(
        blank=True,
        null=True
    )

    telegram_message_link = models.URLField(
        blank=True,
        null=True
    )

    # Movie Information
    year = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    release_date = models.DateField(
        null=True,
        blank=True
    )

    quality = models.CharField(
        max_length=20,
        blank=True
    )

    language = models.CharField(
        max_length=50,
        blank=True
    )

    duration = models.CharField(
        max_length=30,
        blank=True
    )

    imdb_rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True
    )

    description = models.TextField(blank=True)

    poster = models.ImageField(
        upload_to="movie_posters/",
        blank=True,
        null=True
    )

    file_size = models.CharField(
        max_length=30,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="completed"
    )

    # Series Information
    season = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    episode = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    # Search Tags
    tags = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma separated tags"
    )

    # Statistics
    views = models.PositiveIntegerField(default=0)
    downloads = models.PositiveIntegerField(default=0)

    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["year"]),
            models.Index(fields=["quality"]),
            models.Index(fields=["language"]),
            models.Index(fields=["content_type"]),
            models.Index(fields=["is_featured"]),
            models.Index(fields=["created_at"]),
            ]
        
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "telegram_message_id",
                    "channel"
                    ],
                name="unique_channel_message"
                )
             ]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            
            slug = base_slug
            counter = 1
            
            while TelegramMovie.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
                
                self.slug = slug
                
                super().save(*args, **kwargs)
                
    @property
    def can_download_from_website(self):
        
        try:
            return float(self.file_size) <= 2
        
        except Exception:
            return False
                    
    def __str__(self):
        return self.title


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
        unique_together = ("user", "movie")

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
    
