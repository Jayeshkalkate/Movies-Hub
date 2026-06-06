from django.core.management.base import BaseCommand
from telegram import Bot
from django.conf import settings
from coremovieshub.models import TelegramChannel, TelegramMovie

class Command(BaseCommand):
    help = 'Sync movies from Telegram channels into database'

    def handle(self, *args, **options):
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        for channel in TelegramChannel.objects.all():
            self.stdout.write(f"Syncing {channel.name}...")
            # You'll need to fetch messages from the channel – requires bot to be admin.
            # Use bot.get_chat_history(chat_id=channel.chat_id) – not directly available.
            # Instead, implement manual or use Telegram's forward mechanism.
            # For simplicity, use the upload command above for new movies.