from coremovieshub.models import TelegramMovie, TelegramChannel
from django.utils.text import slugify

channel = TelegramChannel.objects.get(
    chat_id="-1003842092188"
)

movie = TelegramMovie.objects.create(
    title="Save Test 2",
    slug=slugify("Save Test 2"),
    content_type="movie",
    category=channel.category,
    channel=channel,
    telegram_message_id=999998,
    telegram_file_id="test",
    telegram_message_link="https://t.me/c/3842092188/999998",
    quality="720p",
    description="Test",
)

print(movie.id)