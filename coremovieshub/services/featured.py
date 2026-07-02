from coremovieshub.models import TelegramMovie


def update_featured_movies(limit=8):
    # Clear existing featured movies
    TelegramMovie.objects.update(is_featured=False)

    # Get the IDs of the top movies
    featured_ids = list(
        TelegramMovie.objects
        .exclude(poster="")
        .exclude(rating__isnull=True)
        .order_by("-rating", "-views", "-created_at")
        .values_list("id", flat=True)[:limit]
    )

    # Update only those IDs
    TelegramMovie.objects.filter(id__in=featured_ids).update(
        is_featured=True
    )