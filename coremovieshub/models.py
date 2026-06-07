# Create your models here.
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class CustomUser(AbstractUser):
    def __str__(self):
        return self.username


# =====================================================
# CATEGORIES
# =====================================================

class Category(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True
    )

    slug = models.SlugField(
        unique=True,
        blank=True
    )

    description = models.TextField(
        blank=True
    )

    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Emoji icon"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


# =====================================================
# WEBSITE VIDEOS (Optional)
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

    membership_status = models.BooleanField(
        default=False
    )

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

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        status = "Verified" if self.membership_status else "Not Verified"
        return f"{self.user.username} - {status}"


# =====================================================
# TELEGRAM CATEGORY CHANNELS
# =====================================================

class TelegramChannel(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True
    )

    chat_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Telegram Channel ID (e.g. -1001234567890)"
    )

    category = models.OneToOneField(
        Category,
        on_delete=models.CASCADE,
        related_name="telegram_channel"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.name} ({self.category.name})"


# =====================================================
# TELEGRAM MOVIES DATABASE
# =====================================================

class TelegramMovie(models.Model):

    CONTENT_TYPES = (
        ("movie", "Movie"),
        ("series", "Series"),
        ("anime", "Anime"),
        ("documentary", "Documentary"),
    )

    title = models.CharField(
        max_length=300
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

    telegram_message_id = models.BigIntegerField()

    telegram_file_id = models.TextField()

    telegram_message_link = models.URLField(
        blank=True,
        null=True
    )

    year = models.IntegerField(
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

    description = models.TextField(
        blank=True
    )

    poster = models.ImageField(
        upload_to="movie_posters/",
        blank=True,
        null=True
    )

    views = models.PositiveIntegerField(
        default=0
    )

    downloads = models.PositiveIntegerField(
        default=0
    )

    is_featured = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
    
