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

from .services.movie_metadata import search_movie_metadata

admin.site.register(CustomUser, UserAdmin)


@admin.action(description="Enrich selected movies")
def enrich_tmdb(modeladmin, request, queryset):
    """
    Fetch metadata from TMDB and update selected movies.
    """

    updated_count = 0

    for movie in queryset:
        try:
            metadata = search_movie_metadata(
                movie.title,
                movie.year,
            )

            if not metadata:
                continue

            # Update fields only if data exists
            movie.description = (
                metadata.get("overview")
                or movie.description
            )

            movie.rating = (
                metadata.get("rating")
                or movie.rating
            )
            
            movie.poster = (
                metadata.get("poster")
                or movie.poster
            )
            
            movie.banner = (
                metadata.get("banner")
                or movie.banner
            )
            
            movie.tmdb_id = (
                metadata.get("tmdb_id")
                or movie.tmdb_id
            )
            
            movie.release_date = (
                metadata.get("release_date")
                or movie.release_date
            )
            
            movie.overview = (
                metadata.get("overview")
                or movie.overview
            )

            movie.save()

            updated_count += 1

        except Exception as exc:
            modeladmin.message_user(
                request,
                f"Failed to enrich '{movie.title}': {exc}",
                level=messages.WARNING,
            )

    modeladmin.message_user(
        request,
        f"Successfully enriched {updated_count} movie(s).",
        level=messages.SUCCESS,
    )


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
        "tmdb_id",           # Added
        "has_tmdb",          # Custom boolean indicator
        "slug",
        "content_type",
        "category",
        "quality",
        "year",
        "duration",
        "rating",
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
        "created_at",
        # tmdb_id intentionally omitted as a filter (integer not ideal)
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

    actions = [
        enrich_tmdb,
    ]

    list_per_page = 100

    ordering = (
        "-created_at",
    )

    date_hierarchy = "created_at"

    list_editable = (
        "is_featured",
    )

    # Custom method to show whether a TMDB ID exists
    def has_tmdb(self, obj):
        return bool(obj.tmdb_id)
    has_tmdb.boolean = True
    has_tmdb.short_description = "Has TMDB ID"