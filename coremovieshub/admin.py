# coremovieshub/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib import messages

from .models import (
    CustomUser,
    Category,
    Video,
    MembershipVerification,
    TelegramChannel,
    TelegramMovie,
)

admin.site.register(CustomUser, UserAdmin)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {
        "slug": ("name",)
    }

    list_display = (
        "name",
        "icon",
        "created_at",
    )

    search_fields = (
        "name",
    )

    ordering = (
        "name",
    )


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "created_at",
    )

    list_filter = (
        "category",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
    )

    ordering = (
        "-created_at",
    )


@admin.register(MembershipVerification)
class MembershipVerificationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "telegram_id",
        "membership_status",
        "verified_at",
    )

    list_filter = (
        "membership_status",
    )

    search_fields = (
        "user__username",
        "telegram_id",
    )

    ordering = (
        "-verified_at",
    )


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "chat_id",
        "category",
    )

    search_fields = (
        "name",
        "chat_id",
    )

    list_filter = (
        "category",
    )

    ordering = (
        "name",
    )


@admin.register(TelegramMovie)
class TelegramMovieAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "rating",
        "year",
        "tmdb_id",
        "status",
        "language",
        "has_tmdb",          # Custom boolean indicator
        "slug",
        "content_type",
        "category",
        "quality",
        "duration",
        "is_featured",
        "views",
        "downloads",
        "created_at",
    )

    list_filter = (
        "content_type",
        "category",
        "quality",
        "is_featured",
        "year",
        "status",
        "language",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "tags",
    )

    prepopulated_fields = {
        "slug": ("title",)
    }

    readonly_fields = (
        "telegram_message_link",
        "telegram_file_id",
        "views",
        "downloads",
        "created_at",
        "updated_at",
    )

    list_per_page = 100

    ordering = (
        "-created_at",
    )

    date_hierarchy = "created_at"

    list_editable = (
        "is_featured",
    )

    def has_tmdb(self, obj):
        return bool(obj.tmdb_id)
    has_tmdb.boolean = True
    has_tmdb.short_description = "Has TMDB ID"