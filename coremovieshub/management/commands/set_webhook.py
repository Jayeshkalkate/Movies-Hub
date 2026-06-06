import requests
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Set Telegram bot webhook'

    def handle(self, *args, **options):
        webhook_url = f"{settings.BASE_URL}/webhook/"
        token = settings.TELEGRAM_BOT_TOKEN
        url = f"https://api.telegram.org/bot{token}/setWebhook"
        response = requests.post(url, data={'url': webhook_url})
        self.stdout.write(str(response.json()))