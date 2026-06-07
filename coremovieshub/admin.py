# Register your models here.

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    CustomUser,
    Category,
    Video,
    MembershipVerification,
    TelegramChannel,
    TelegramMovie
)

admin.site.register(CustomUser, UserAdmin)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {
        'slug': ('name',)
    }

    list_display = (
        'name',
        'icon',
        'created_at'
    )

    search_fields = (
        'name',
    )


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'category',
        'created_at'
    )

    list_filter = (
        'category',
        'created_at'
    )

    search_fields = (
        'title',
        'description'
    )


@admin.register(MembershipVerification)
class MembershipVerificationAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'telegram_id',
        'membership_status',
        'verified_at'
    )

    list_filter = (
        'membership_status',
    )

    search_fields = (
        'user__username',
        'telegram_id'
    )


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'chat_id',
        'category'
    )

    search_fields = (
        'name',
        'chat_id'
    )


@admin.register(TelegramMovie)
class TelegramMovieAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'content_type',
        'category',
        'quality',
        'year',
        'views',
        'downloads',
        'created_at'
    )

    list_filter = (
        'content_type',
        'category',
        'quality',
        'created_at'
    )

    search_fields = (
        'title',
        'description'
    )
